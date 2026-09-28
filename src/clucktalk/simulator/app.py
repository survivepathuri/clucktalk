"""CluckTalk Simulator: a local web app that plays the Alexa+ client role (docs/DESIGN.md §2, §15).

The browser page is the device (Echo Show with a screen, or Echo Dot voice-only): speech in, speech out, and the
MCP App card on screen. This backend is the host's cloud side: it understands the utterance (mock mode: a visible
rule-based matcher, clucktalk.simulator.intents), calls the CluckTalk MCP server over Streamable HTTP, and returns
the spoken answer, the tool result and the exact JSON-RPC exchanges for the developer panel.

MCP Apps host duties (spec 2026-01-26, "Sandbox proxy"): a web host MUST render the card through a sandbox proxy
on a different origin. The page runs on one loopback name (127.0.0.1 or localhost) and loads the proxy from the
other, so the two origins differ on one port. The proxy's CSP is built from the card's declared ``_meta.ui.csp``.

Demo mode only (MOCK_BEDROCK=true). The live host (Bedrock Converse + Polly) belongs to the AWS setup task; until
then live mode refuses to start rather than pretending (Rule 6).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from clucktalk.config import APP_NAME
from clucktalk.simulator.intents import match, normalise
from clucktalk.simulator.mcp_client import Exchange, McpClient, McpUnavailable

logger = logging.getLogger("clucktalk.simulator")
STATIC = Path(__file__).resolve().parent / "static"
LOOPBACK_NAMES = ("127.0.0.1", "localhost")
MAX_SIMULATED_DELAY_MS = 8000
# Host wording (not CluckTalk's): what the device says when no tool fits, or the add-on is down.
FALLBACK_SPEECH = (
    f"Sorry, {APP_NAME} can't help with that yet. You can ask how a shed is doing, "
    f"for a feed plan, or what {APP_NAME} can do."
)
UNAVAILABLE_SPEECH = f"Sorry, {APP_NAME} isn't responding right now. Please try again in a moment."
PROTOCOL_ERROR_SPEECH = f"Sorry, {APP_NAME} couldn't do that just now. Please try again in a moment."
VIEW_METHODS = {"tools/call", "resources/read"}  # what a card may ask the host to forward (spec: standard messages)


@dataclass(frozen=True)
class SimulatorSettings:
    port: int
    mcp_url: str
    auth_token: str | None
    interim_after_ms: int = 1000  # show "Still working..." when a turn takes longer than this

    @property
    def origins(self) -> set[str]:
        return {f"http://{n}:{self.port}" for n in LOOPBACK_NAMES}

    @property
    def hosts(self) -> set[str]:
        return {f"{n}:{self.port}" for n in LOOPBACK_NAMES}


# ---------------------------------------------------------------------------------------------------------------
# Sandbox CSP (spec: "Host MUST construct CSP headers based on declared domains"; restrictive default otherwise)
# ---------------------------------------------------------------------------------------------------------------
_CSP_ORIGIN = re.compile(r"^https://(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)*(:\d{1,5})?$")


def _origins(values: Any) -> list[str]:
    """Declared origins that are plain https origins; anything else is dropped (and logged), never loosened."""
    if not isinstance(values, list):
        return []
    good = [v for v in values if isinstance(v, str) and _CSP_ORIGIN.match(v)]
    if len(good) != len(values):
        logger.warning("dropped invalid CSP origins: %s", [v for v in values if v not in good])
    return good


def sandbox_csp(declared: dict[str, Any] | None, ancestors: tuple[str, ...] = (), *, strict: bool = False) -> str:
    """The spec's restrictive default, plus declared origins. One addition the spec's default lacks:
    ``font-src 'self' data:``, as in the ext-apps reference host (FRICTION_LOG FL-007), so a card can bundle a
    font inline. Nothing from the network is allowed unless the card declares it.

    ``strict=True`` drops that addition and behaves like a host that applies the spec's default literally: fonts
    load only from declared ``resourceDomains`` (the spec maps them to ``font-src``), so inlined data: fonts are
    blocked (``font-src`` falls back to ``default-src 'none'``). Used to test a card's font fallback.

    Two host-side hardenings: ``form-action 'none'`` (``default-src`` does not cover form posts, so a card could
    otherwise post to the Simulator's own API) and ``frame-ancestors`` limited to the Simulator page, so no other
    local page can embed the proxy and feed it HTML."""
    declared = declared or {}
    res = " ".join(_origins(declared.get("resourceDomains")))
    connect = " ".join(_origins(declared.get("connectDomains"))) or "'none'"
    frame = " ".join(_origins(declared.get("frameDomains"))) or "'none'"
    base = " ".join(_origins(declared.get("baseUriDomains"))) or "'self'"
    embedders = " ".join(ancestors) or "'none'"
    if strict:
        fonts = [f"font-src {res}"] if res else []  # no directive: falls back to default-src 'none'
    else:
        fonts = [f"font-src 'self' data: {res}".strip()]
    directives = [
        "default-src 'none'",
        f"script-src 'self' 'unsafe-inline' {res}".strip(),
        f"style-src 'self' 'unsafe-inline' {res}".strip(),
        f"img-src 'self' data: {res}".strip(),
        f"media-src 'self' data: {res}".strip(),
        *fonts,
        f"connect-src {connect}",
        f"frame-src {frame}",
        f"base-uri {base}",
        "object-src 'none'",
        "form-action 'none'",
        f"frame-ancestors {embedders}",
    ]
    return "; ".join(directives)


# ---------------------------------------------------------------------------------------------------------------
# Request guard: loopback Host names only, and API calls only from the Simulator's own page
# ---------------------------------------------------------------------------------------------------------------
class LocalOnly:
    def __init__(self, app: ASGIApp, settings: SimulatorSettings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
            if headers.get("host") not in self.settings.hosts:
                await JSONResponse({"error": "unknown host"}, status_code=421)(scope, receive, send)
                return
            if scope["path"].startswith("/api/") and scope["method"] != "GET":
                # Only the Simulator page itself: same origin as the requested host (the card's sandbox origin
                # never calls the API), and JSON bodies only, which a plain HTML form cannot send.
                if headers.get("origin") != f"http://{headers.get('host')}":
                    await JSONResponse({"error": "forbidden origin"}, status_code=403)(scope, receive, send)
                    return
                if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                    await JSONResponse({"error": "JSON body required"}, status_code=415)(scope, receive, send)
                    return
            if scope["path"].startswith("/static/"):
                send = _revalidate(send)  # always check for an updated page script/style (ETag makes it cheap)
        await self.app(scope, receive, send)


def _revalidate(send: Send) -> Send:
    async def wrapped(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-cache")]
        await send(message)

    return wrapped


# ---------------------------------------------------------------------------------------------------------------
# Turn handling
# ---------------------------------------------------------------------------------------------------------------
def _spoken(result: dict[str, Any]) -> str:
    return " ".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text").strip()


async def _json_object(request: Request) -> dict[str, Any] | None:
    """The request body as a JSON object, or None if it is not one (the caller answers 400)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        logger.info("rejected non-JSON body: %s", err)
        return None
    return body if isinstance(body, dict) else None


def _is_int_or_none(v: Any) -> bool:
    return v is None or (isinstance(v, int) and not isinstance(v, bool))


def _mcp_ms(exchanges: list[Exchange]) -> float:
    return round(sum(e.ms for e in exchanges), 1)


def build_app(settings: SimulatorSettings, client: McpClient | None = None) -> ASGIApp:
    mcp = client or McpClient(settings.mcp_url, settings.auth_token)
    lock = asyncio.Lock()  # one conversation at a time, like one device

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        try:
            async with lock:
                await mcp.connect()
            logger.info("connected to %s at %s", mcp.server_info.get("name"), settings.mcp_url)
        except McpUnavailable as err:  # not fatal: the device says so on the first turn and retries then
            logger.warning("%s", err)
        yield
        await mcp.aclose()

    async def index(_request: Request) -> Response:
        return FileResponse(STATIC / "index.html", headers={"cache-control": "no-store"})

    async def sandbox(request: Request) -> Response:
        try:
            declared = json.loads(request.query_params.get("csp") or "{}")
        except json.JSONDecodeError:
            return JSONResponse({"error": "csp must be JSON"}, status_code=400)
        return FileResponse(
            STATIC / "sandbox.html",
            headers={
                "content-security-policy": sandbox_csp(
                    declared, tuple(sorted(settings.origins)), strict=request.query_params.get("strict") == "1"
                ),
                "cache-control": "no-store",
            },
        )

    async def state(_request: Request) -> Response:
        tools = [{"name": n, "resourceUri": mcp.resource_uri(n)} for n in mcp.tools]
        return JSONResponse(
            {
                "app_name": APP_NAME,
                "mode": "demo",
                "mcp_url": settings.mcp_url,
                "connected": bool(mcp.tools),
                "server_info": mcp.server_info,
                "tools": tools,
                "interim_after_ms": settings.interim_after_ms,
            }
        )

    async def turn(request: Request) -> Response:
        started = time.perf_counter()
        body = await _json_object(request)
        delay_raw = body.get("simulate_delay_ms") if body is not None else None
        if body is None or not isinstance(body.get("utterance", ""), str) or not _is_int_or_none(delay_raw):
            return JSONResponse(
                {"error": "expected {utterance: string, device?, simulate_delay_ms?: int}"}, status_code=400
            )
        utterance = body.get("utterance", "")[:500]
        device = "dot" if body.get("device") == "dot" else "show"
        delay = max(0, min(delay_raw or 0, MAX_SIMULATED_DELAY_MS))
        intent = match(utterance)
        out: dict[str, Any] = {
            "utterance": utterance,
            "normalised": normalise(utterance),
            "device": device,
            "intent": None
            if intent is None
            else {"tool": intent.tool, "arguments": intent.arguments, "rule": intent.rule},
            "exchanges": [],
            "card": None,
            "result": None,
            "is_error": False,
            "timing": {"simulated_delay_ms": delay},
        }
        if intent is None:
            out.update(kind="fallback", speech=FALLBACK_SPEECH)
        else:
            if delay:
                await asyncio.sleep(delay / 1000)  # visible test control: labeled in the developer panel
            try:
                async with lock:
                    log = await mcp.request("tools/call", {"name": intent.tool, "arguments": intent.arguments})
                response = log[-1].response or {}
                out["exchanges"] = [e.as_dict() for e in log]
                out["timing"]["mcp_ms"] = round(log[-1].ms, 1)
                if "result" not in response:  # JSON-RPC protocol error: the server answered but refused the call
                    err = response.get("error") or {}
                    out.update(
                        kind="protocol_error",
                        speech=PROTOCOL_ERROR_SPEECH,
                        is_error=True,
                        detail=f"JSON-RPC error {err.get('code')}: {err.get('message')}",
                    )
                else:
                    result = response["result"]
                    uri = mcp.resource_uri(intent.tool)
                    out.update(kind="tool", result=result, speech=_spoken(result), is_error=bool(result.get("isError")))
                    if device == "show" and uri:
                        out["card"] = {"uri": uri, "tool": mcp.tools[intent.tool]}
            except McpUnavailable as err:
                logger.warning("turn failed: %s", err)
                out.update(kind="unavailable", speech=UNAVAILABLE_SPEECH, is_error=True, detail=str(err))
        out["timing"]["backend_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return JSONResponse(out)

    async def resource(request: Request) -> Response:
        uri = request.query_params.get("uri", "")
        if not uri.startswith("ui://"):
            return JSONResponse({"error": "only ui:// resources"}, status_code=400)
        try:
            async with lock:
                content, log = await mcp.read_ui_resource(uri)
        except McpUnavailable as err:
            return JSONResponse({"error": str(err)}, status_code=502)
        return JSONResponse({"content": content, "exchanges": [e.as_dict() for e in log], "mcp_ms": _mcp_ms(log)})

    async def view_request(request: Request) -> Response:
        """A card's own request (tap = voice), forwarded to the MCP server like any host would."""
        body = await _json_object(request)
        if body is None or not isinstance(body.get("params") or {}, dict):
            return JSONResponse({"error": {"code": -32600, "message": "invalid request"}}, status_code=400)
        method, params, card_uri = body.get("method"), body.get("params") or {}, body.get("card_uri")
        if method not in VIEW_METHODS:
            return JSONResponse({"error": {"code": -32601, "message": f"{method} is not forwarded"}}, status_code=400)
        if method == "tools/call":
            # A card may only call the tool that owns it (so a tap can never, e.g., confirm an order that needs a
            # spoken "yes"), and only if the tool is visible to apps.
            name = params.get("name")
            visibility = ((mcp.tools.get(name) or {}).get("_meta") or {}).get("ui", {}).get("visibility")
            owns_card = isinstance(card_uri, str) and mcp.resource_uri(name) == card_uri
            if name not in mcp.tools or not owns_card or (visibility is not None and "app" not in visibility):
                return JSONResponse(
                    {"error": {"code": -32602, "message": "tool not callable from a card"}}, status_code=400
                )
        if method == "resources/read" and not str(params.get("uri", "")).startswith("ui://"):
            return JSONResponse({"error": {"code": -32602, "message": "only ui:// resources"}}, status_code=400)
        try:
            async with lock:
                log = await mcp.request(method, params)
        except McpUnavailable as err:
            return JSONResponse({"error": {"code": -32000, "message": str(err)}}, status_code=502)
        response = log[-1].response or {}
        return JSONResponse(
            {"response": response, "exchanges": [e.as_dict() for e in log], "mcp_ms": round(log[-1].ms, 1)}
        )

    app = Starlette(
        routes=[
            Route("/", index),
            Route("/sandbox", sandbox),
            Route("/api/state", state),
            Route("/api/turn", turn, methods=["POST"]),
            Route("/api/resource", resource),
            Route("/api/view-request", view_request, methods=["POST"]),
            Mount("/static", StaticFiles(directory=STATIC), name="static"),
        ],
        lifespan=lifespan,
    )
    return LocalOnly(app, settings)
