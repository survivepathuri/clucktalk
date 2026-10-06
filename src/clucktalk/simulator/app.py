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
import hashlib
import hmac
import json
import logging
import math
import os
import re
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from clucktalk.config import APP_NAME, APP_NAME_TE
from clucktalk.domain.photos import PHOTO_REFS
from clucktalk.domain.triage import SIGN_TEXT, Sign
from clucktalk.i18n import GENERIC_ERROR, GENERIC_NEXT_STEP, PILOT_BADGE
from clucktalk.i18n.pilot import (
    CHIPS,
    HEALTH_READBACK,
    HOST_NOT_STARTED,
    NOT_UNDERSTOOD,
    NOTHING_PENDING,
    OUTCOMES,
    PILOT_UI,
    SHED_LABEL,
)
from clucktalk.simulator.intents import Intent, match, normalise, yes_no
from clucktalk.simulator.intents_te import chip_intent, match_te, yes_no_te
from clucktalk.simulator.mcp_client import Exchange, McpClient, McpUnavailable
from clucktalk.usage import UsageCounters

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
NOTHING_TO_ANSWER_SPEECH = "There's nothing waiting for a yes or no right now. What would you like to do?"
PROTOCOL_ERROR_SPEECH = f"Sorry, {APP_NAME} couldn't do that just now. Please try again in a moment."
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")  # the page makes one random token per browser tab
DEFAULT_SESSION = "default"  # the demo is one device: one conversation
VIEW_METHODS = {"tools/call", "resources/read"}  # what a card may ask the host to forward (spec: standard messages)


@dataclass(frozen=True)
class SimulatorSettings:
    port: int
    mcp_url: str
    auth_token: str | None
    interim_after_ms: int = 1000  # show "Still working..." when a turn takes longer than this
    mode: str = "demo"  # "pilot": the farmer's own farm, so the page must never say "Demo data" or "fictional"
    # Hardening (Step 51 part D). Off for the demo unless a token is given; the pilot always has a token.
    tokens: tuple[str, ...] = ()  # bearer tokens, one per farmer; every /api/ call needs one of them
    public_origin: str | None = None  # the real https origin behind the proxy, e.g. https://pilot.example.org
    rate_per_minute: int = 60  # requests per token per minute
    max_sessions: int = 20  # browser sessions kept at once
    max_body: int = 8192  # bytes in a request body
    disabled_file: Path | None = None  # the kill switch: this file existing pauses the Simulator
    usage_path: Path | None = None  # anonymous usage counters (pilot)

    @property
    def origins(self) -> set[str]:
        return {f"http://{n}:{self.port}" for n in LOOPBACK_NAMES}

    @property
    def public_host(self) -> str | None:
        return None if self.public_origin is None else self.public_origin.removeprefix("https://")

    @property
    def allowed_origins(self) -> set[str]:
        """Every origin an API call may come from: the loopback pages, and the real https origin when there is one."""
        return self.origins | ({self.public_origin} if self.public_origin else set())

    @property
    def hosts(self) -> set[str]:
        public = {self.public_host} if self.public_host else set()
        return {f"{n}:{self.port}" for n in LOOPBACK_NAMES} | public  # type: ignore[misc]

    @property
    def hardened(self) -> bool:
        return bool(self.tokens)


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
                host = headers.get("host")
                # The real hostname is https only (the proxy ends TLS there); the loopback names are http.
                expected = self.settings.public_origin if host == self.settings.public_host else f"http://{host}"
                if headers.get("origin") != expected:
                    await JSONResponse({"error": "forbidden origin"}, status_code=403)(scope, receive, send)
                    return
                if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                    await JSONResponse({"error": "JSON body required"}, status_code=415)(scope, receive, send)
                    return
            if scope["path"].startswith("/static/"):
                send = _revalidate(send)  # always check for an updated page script/style (ETag makes it cheap)
        await self.app(scope, receive, send)


DEMO_BADGE_HTML = (
    '<div class="mode" id="mode" role="note" title="MOCK_BEDROCK=true: fictional seeded farm, rule-based host">'
    "Demo data · mock host</div>"
)
DEMO_FOOTER_SENTENCE = " The farm is fictional demo data."


def pilot_page(html: str) -> str:
    """The Simulator page for a pilot: the pilot badge instead of "Demo data · mock host", and no sentence saying the
    farm is fictional. If the page no longer has the exact demo wording this raises, so a stale badge can never ship."""
    if DEMO_BADGE_HTML not in html or DEMO_FOOTER_SENTENCE not in html:
        raise RuntimeError("index.html no longer has the demo badge or footer wording the pilot page replaces")
    badge = (
        '<div class="mode" id="mode" role="note" title="Pilot: the farmer&#39;s own farm, no demo data">'
        f"{PILOT_BADGE.en}</div>"
    )
    return html.replace(DEMO_BADGE_HTML, badge).replace(DEMO_FOOTER_SENTENCE, "")


def paused(settings: SimulatorSettings) -> bool:
    """The kill switch, read at every request: the CLUCKTALK_DISABLED variable, or the disabled file existing."""
    if os.environ.get("CLUCKTALK_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return True
    return settings.disabled_file is not None and settings.disabled_file.exists()


FAILED_AUTH_PER_MINUTE = 20  # wrong or missing tokens, all together: guessing is slow
WINDOW_SECONDS = 60.0
SESSION_IDLE_SECONDS = 3600.0


class Hardening:
    """In front of the app when a token is configured, after the host and origin checks (LocalOnly):

    * the kill switch: everything but /healthz answers 503 while it is on;
    * a request body over ``max_body`` bytes is refused with 413 (whether or not it says how big it is);
    * every /api/ call needs ``Authorization: Bearer <token>``: compared in constant time against every configured
      token, with no early exit, and the answer never says whether the token or the header was wrong (401);
    * every /api/ call is counted per token (a hash, never the token): over ``rate_per_minute`` is 429 with Retry-After.
    Nothing here logs a header, a body or a token."""

    def __init__(self, app: ASGIApp, settings: SimulatorSettings, clock: Callable[[], float]) -> None:
        self.app, self.settings, self.clock = app, settings, clock
        self.windows: dict[str, deque[float]] = {}

    def _allow(self, key: str, limit: int) -> int:
        """0 when the call is allowed, else the seconds to wait."""
        now = self.clock()
        window = self.windows.setdefault(key, deque())
        while window and now - window[0] >= WINDOW_SECONDS:
            window.popleft()
        if len(window) >= limit:
            return max(1, math.ceil(WINDOW_SECONDS - (now - window[0])))
        window.append(now)
        return 0

    def _token_ok(self, header: str) -> tuple[bool, str]:
        presented = header[len("Bearer ") :] if header.startswith("Bearer ") else ""
        if " " in presented:
            presented = ""
        ok = False
        for token in self.settings.tokens:  # every token, always: no early exit to time
            ok |= hmac.compare_digest(presented.encode("utf-8"), token.encode("utf-8"))
        key = hashlib.sha256(presented.encode("utf-8")).hexdigest()[:16] if ok else "anonymous"
        return ok, key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.settings.hardened:
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if path != "/healthz":
            if paused(self.settings):
                await JSONResponse({"error": "paused"}, status_code=503)(scope, receive, send)
                return
            if scope["method"] in ("POST", "PUT", "PATCH"):
                receive = await self._bounded(scope, receive, send)
                if receive is None:
                    return
            if path.startswith("/api/"):
                headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
                ok, key = self._token_ok(headers.get("authorization", ""))
                wait = self._allow(key, self.settings.rate_per_minute if ok else FAILED_AUTH_PER_MINUTE)
                if wait:
                    await JSONResponse(
                        {"error": "too many requests"}, status_code=429, headers={"retry-after": str(wait)}
                    )(scope, receive, send)
                    return
                if not ok:
                    await JSONResponse(
                        {"error": "unauthorized"}, status_code=401, headers={"www-authenticate": "Bearer"}
                    )(scope, receive, send)
                    return
        await self.app(scope, receive, send)

    async def _bounded(self, scope: Scope, receive: Receive, send: Send) -> Receive | None:
        """The whole body if it is small enough (handed on again), else None after answering 413."""
        limit = self.settings.max_body
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        declared = headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"error": "request too large"}, status_code=413)(scope, receive, send)
            return None
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await JSONResponse({"error": "request too large"}, status_code=413)(scope, receive, send)
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        sent = [False]

        async def replay() -> dict[str, Any]:
            if sent[0]:
                return {"type": "http.disconnect"}
            sent[0] = True
            return {"type": "http.request", "body": body, "more_body": False}

        return replay


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


@dataclass
class Conversation:
    """One browser session's conversation: the read-back awaiting its yes or no, and the turn counter. Never shared
    between sessions, so two phones can never answer each other's read-back (the demo has the one default session)."""

    last_used: float = 0.0  # when the session was last used (for the cap and the idle clean-up)
    pending: dict[str, Any] = field(default_factory=dict)  # a server read-back: tool, arguments, proposal_id
    host_pending: dict[str, Any] = field(default_factory=dict)  # a host read-back (starting a health check)
    turns: int = 0


def _spoken_te(result: dict[str, Any]) -> str:
    """The Telugu of a tool result: its text_te, or the Telugu of its error message and next step."""
    sc = result.get("structuredContent") or {}
    if sc.get("text_te"):
        return str(sc["text_te"])
    meta = (result.get("_meta") or {}).get("clucktalk/error") or {}
    return " ".join(x for x in (meta.get("message_te"), meta.get("next_step_te")) if x).strip()


GENERIC_TE = f"{GENERIC_ERROR.te} {GENERIC_NEXT_STEP.te}"


def _mcp_ms(exchanges: list[Exchange]) -> float:
    return round(sum(e.ms for e in exchanges), 1)


def build_app(
    settings: SimulatorSettings, client: McpClient | None = None, clock: Callable[[], float] = time.monotonic
) -> ASGIApp:
    mcp = client or McpClient(settings.mcp_url, settings.auth_token)
    lock = asyncio.Lock()  # one call to the MCP server at a time (its session is shared by every browser)
    conversations: dict[str, Conversation] = {}  # per browser session: never shared between two browsers
    pilot = settings.mode == "pilot"
    usage = UsageCounters(settings.usage_path) if settings.usage_path is not None else None  # damaged: fails loud

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

    page = pilot_page((STATIC / "index.html").read_text(encoding="utf-8")) if settings.mode == "pilot" else None

    pilot_home = (
        (STATIC / "pilot.html")
        .read_text(encoding="utf-8")
        .replace("@BADGE_EN@", PILOT_BADGE.en)
        .replace("@BADGE_TE@", PILOT_BADGE.te)
        .replace("@APP_NAME_TE@", APP_NAME_TE)
        if pilot
        else None
    )

    async def index(_request: Request) -> Response:
        if pilot_home is not None:  # the farmer's phone page; the developer page is at /desktop
            return Response(pilot_home, media_type="text/html", headers={"cache-control": "no-store"})
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

    async def healthz(_request: Request) -> Response:
        """Is it up: no data, no farm, no token. "disabled" while the kill switch is on."""
        return JSONResponse({"status": "disabled" if paused(settings) else "ok", "mode": settings.mode})

    async def state(_request: Request) -> Response:
        tools = [{"name": n, "resourceUri": mcp.resource_uri(n)} for n in mcp.tools]
        return JSONResponse(
            {
                "app_name": APP_NAME,
                "mode": settings.mode,
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
        photo_ref = body.get("photo_ref") if body is not None else None
        if (
            body is None
            or not isinstance(body.get("utterance", ""), str)
            or not _is_int_or_none(delay_raw)
            or (photo_ref is not None and photo_ref not in PHOTO_REFS)
        ):
            return JSONResponse(
                {"error": "expected {utterance: string, device?, simulate_delay_ms?: int, photo_ref?: string}"},
                status_code=400,
            )
        lang, chip, params, session = body.get("lang"), body.get("chip"), body.get("params", {}), body.get("session")
        if (
            lang not in (None, "en", "te")
            or (chip is not None and not isinstance(chip, str))
            or not isinstance(params, dict)
            or (session is not None and not (isinstance(session, str) and SESSION_RE.match(session)))
        ):
            return JSONResponse(
                {"error": "expected lang: en or te, chip?: string, params?: object, session?: 16-64 letters or digits"},
                status_code=400,
            )
        if not pilot and (lang == "te" or chip is not None):
            return JSONResponse({"error": "Telugu input and chips are only in pilot mode"}, status_code=400)
        if pilot and session is None:
            return JSONResponse({"error": "a session is required"}, status_code=400)
        te = lang == "te"
        intent: Intent | None = None
        answer: str | None = None
        routed = None
        if chip is not None:  # a tapped chip: validated here, never through a text matcher
            if chip in ("yes", "no"):
                answer = chip
            else:
                try:
                    intent = chip_intent(chip, params)
                except ValueError as err:
                    return JSONResponse({"error": f"bad chip: {err}"}, status_code=400)
        utterance = body.get("utterance", "")[:500]
        device = "dot" if body.get("device") == "dot" else "show"
        delay = max(0, min(delay_raw or 0, MAX_SIMULATED_DELAY_MS))
        key = session or DEFAULT_SESSION
        if key not in conversations:
            now = clock()
            for stale in [k for k, c in conversations.items() if now - c.last_used > SESSION_IDLE_SECONDS]:
                del conversations[stale]
            if len(conversations) >= settings.max_sessions:
                return JSONResponse({"error": "too many sessions"}, status_code=503)
        conv = conversations.setdefault(key, Conversation())
        conv.last_used = clock()
        if usage is not None:
            usage.record_turn()
        # docs/DESIGN.md §5.1: a bare yes/no answers the pending read-back (same tool + proposal_id + answer).
        # Anything else moves on, so the old read-back can no longer be confirmed from here.
        if chip is None and te:
            answer = yes_no_te(utterance)
            routed = None if answer is not None else match_te(utterance)
        elif chip is None:
            answer = yes_no(utterance)
        awaiting, host_awaiting = dict(conv.pending), dict(conv.host_pending)
        conv.pending.clear()
        conv.host_pending.clear()
        conv.turns += 1
        this_turn = conv.turns
        if chip is None and not te and answer is None:
            intent = match(utterance)
        if routed is not None and routed.kind == "intent":
            intent = routed.intent
        if answer is not None and awaiting:
            args = {**awaiting["arguments"], "proposal_id": awaiting["proposal_id"], "answer": answer}
            intent = Intent(awaiting["tool"], args, f"answer '{answer}' to the pending read-back")
        elif answer == "yes" and host_awaiting:
            intent = Intent(host_awaiting["tool"], host_awaiting["arguments"], "answer 'yes' to the host read-back")
        if photo_ref and intent is not None and intent.tool == "start_health_check":
            # The farmer attached a (placeholder) photo to this turn; only a new health check takes it.
            intent = Intent(
                intent.tool, {**intent.arguments, "photo_ref": photo_ref}, intent.rule + " + photo attached"
            )
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
        host_read_back = (
            intent is not None
            and intent.tool == "start_health_check"
            and (te or chip is not None)
            and not (answer == "yes" and host_awaiting)
        )
        if host_read_back and intent is not None:
            number = intent.arguments["house"].split()[-1]
            signs = ", ".join(SIGN_TEXT[Sign(s)].te for s in intent.arguments["signs"])
            conv.host_pending.update(tool=intent.tool, arguments=intent.arguments)
            out.update(
                kind="host_readback",
                speech=HEALTH_READBACK.en.format(
                    shed=SHED_LABEL.en.format(number=number), signs=", ".join(intent.arguments["signs"])
                ),
                speech_te=HEALTH_READBACK.te.format(shed=SHED_LABEL.te.format(number=number), signs=signs),
                awaiting_answer=True,
            )
        elif routed is not None and routed.kind == "choose" and routed.chip is not None:
            out.update(
                kind="choose", speech="", speech_te="", choose={"chip": routed.chip.value, "params": routed.params}
            )
        elif intent is None:
            if answer is not None and host_awaiting:
                out.update(kind="fallback", speech=HOST_NOT_STARTED.en, speech_te=HOST_NOT_STARTED.te)
            elif te or chip is not None:
                said = NOTHING_PENDING if answer is not None else NOT_UNDERSTOOD
                out.update(kind="fallback", speech=said.en, speech_te=said.te)
            else:
                out.update(kind="fallback", speech=NOTHING_TO_ANSWER_SPEECH if answer is not None else FALLBACK_SPEECH)
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
                    if te or chip is not None:
                        out["speech_te"] = GENERIC_TE
                else:
                    result = response["result"]
                    uri = mcp.resource_uri(intent.tool)
                    out.update(kind="tool", result=result, speech=_spoken(result), is_error=bool(result.get("isError")))
                    if te or chip is not None:
                        out["speech_te"] = _spoken_te(result)
                    sc = result.get("structuredContent") or {}
                    if (
                        sc.get("status") == "needs_confirmation"
                        and isinstance(sc.get("proposal_id"), str)
                        and this_turn == conv.turns  # the farmer has not moved on while this call ran
                    ):
                        change = {k: v for k, v in intent.arguments.items() if k not in ("proposal_id", "answer")}
                        conv.pending.update(tool=intent.tool, arguments=change, proposal_id=sc["proposal_id"])
                        out["awaiting_answer"] = True
                    if device == "show" and uri:
                        out["card"] = {"uri": uri, "tool": mcp.tools[intent.tool]}
            except McpUnavailable as err:
                logger.warning("turn failed: %s", err)
                out.update(kind="unavailable", speech=UNAVAILABLE_SPEECH, is_error=True, detail=str(err))
                if te or chip is not None:
                    out["speech_te"] = GENERIC_TE
        if usage is not None and answer is not None and (awaiting or host_awaiting):
            sc_done = (out.get("result") or {}).get("structuredContent") or {}
            saved = answer == "yes" and bool(awaiting) and awaiting.get("tool") == "log_daily_record"
            usage.record_answer(answer, saved and sc_done.get("status") == "changed")
        elif usage is not None and out.get("kind") == "tool" and not out.get("is_error"):
            usage.record_result(out["intent"]["tool"], (out.get("result") or {}).get("structuredContent") or {})
        out["timing"]["backend_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return JSONResponse(out)

    async def pilot_ui(_request: Request) -> Response:
        """The pilot page's words, chips, signs and the farmer's sheds (from the tools, never invented here)."""
        if not pilot:
            return JSONResponse({"error": "pilot mode only"}, status_code=404)
        houses: list[dict[str, Any]] = []
        try:
            async with lock:
                log = await mcp.request("tools/call", {"name": "get_record_book", "arguments": {}})
            sc = ((log[-1].response or {}).get("result") or {}).get("structuredContent") or {}
            houses = [{"number": e["number"], "label_te": e["label_te"]} for e in sc.get("entries", [])]
        except McpUnavailable as err:
            logger.warning("pilot page could not list the sheds: %s", err)
        return JSONResponse(
            {
                "strings": {k: {"en": t.en, "te": t.te} for k, t in PILOT_UI.items()},
                "chips": {k: {"en": t.en, "te": t.te} for k, t in CHIPS.items()},
                "outcomes": {k: {"en": t.en, "te": t.te} for k, t in OUTCOMES.items()},
                "signs": [{"code": s.value, "label_te": SIGN_TEXT[s].te} for s in Sign],
                "houses": houses,
            }
        )

    async def desktop(_request: Request) -> Response:
        """The developer page (device mock, panel), kept for the builder; pilot mode only."""
        if page is None or settings.hardened:  # the developer page cannot send a token: off when hardened
            return JSONResponse({"error": "not available"}, status_code=404)
        return Response(page, media_type="text/html", headers={"cache-control": "no-store"})

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
            Route("/healthz", healthz),
            Route("/desktop", desktop),
            Route("/api/pilot/ui", pilot_ui),
            Route("/api/turn", turn, methods=["POST"]),
            Route("/api/resource", resource),
            Route("/api/view-request", view_request, methods=["POST"]),
            Mount("/static", StaticFiles(directory=STATIC), name="static"),
        ],
        lifespan=lifespan,
    )
    return LocalOnly(Hardening(app, settings, clock), settings)
