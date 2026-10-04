"""Server factory and entry point (docs/DESIGN.md §2-§4).

Layers, outermost first:
1. ``BearerAuth``: when CLUCKTALK_AUTH_TOKEN is set (required off-localhost by config), every request
   must carry ``Authorization: Bearer <token>``.
2. ``ProtocolVersionGate``: only initialize-handshake protocol versions reach the SDK. The SDK would route a
   2026-07-28 header to its stateless path; CluckTalk targets 2025-11-25 (docs/VERSIONS.md).
3. ``ProtocolErrorGate``: the SDK's protocol-level answers that echo the input or library text (a body that is not
   JSON, a body that is not a JSON-RPC request, an unknown method name) become short fixed JSON-RPC errors. No
   tool result is touched.
4. SDK Streamable HTTP app with explicit Host/Origin allow-lists (DNS-rebinding protection) and sessions.

Run (Windows):  python tasks.py serve
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sqlite3
import sys

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http import MCP_PROTOCOL_VERSION_HEADER
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, LATEST_HANDSHAKE_VERSION
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from clucktalk.agents import AiServices, demo_ai, live_ai
from clucktalk.config import APP_NAME, ConfigError, Settings, load_settings
from clucktalk.server.errors import SafeToolErrors
from clucktalk.server.farm_state import DemoClock, DemoFarmSource
from clucktalk.server.tools import (
    CapabilityRegistry,
    briefing,
    contract_terms,
    farm_status,
    feed,
    follow_up,
    health,
    profile,
    records,
    sale,
)
from clucktalk.server.tools import help as help_tool
from clucktalk.server.weather import MockForecast, WeatherConfigError, weather_from_env
from clucktalk.store import StoreError
from clucktalk.store.sqlite import SqliteStore

logger = logging.getLogger("clucktalk.server")

TARGET_PROTOCOL_VERSION = "2025-11-25"
MCP_PATH = "/mcp"
_LOCAL_HOST_NAMES = ("127.0.0.1", "localhost", "[::1]")

# The target must stay the SDK's newest handshake version; fail at import if a future pin changes that.
if TARGET_PROTOCOL_VERSION != LATEST_HANDSHAKE_VERSION:
    raise RuntimeError(
        f"mcp SDK's newest handshake version is {LATEST_HANDSHAKE_VERSION}, CluckTalk targets "
        f"{TARGET_PROTOCOL_VERSION}. Re-verify docs/VERSIONS.md before changing either."
    )


def build_mcp_server(source: DemoFarmSource | None = None, ai: AiServices | None = None) -> MCPServer:
    """``source`` defaults to the demo farm as of today (IST); tests pass one with a fixed clock. ``ai`` defaults
    to demo mode (no model calls); ``main`` passes live AI only when chosen explicitly (docs/DESIGN.md §18)."""
    source = source or DemoFarmSource()
    ai = ai or demo_ai()
    guard = SafeToolErrors(
        strict_arguments_for=frozenset({contract_terms.TOOL, follow_up.TOOL}),
        demo_clock_days=lambda: source.demo_clock_days,
    )
    registry = CapabilityRegistry()
    apps = Apps()  # MCP Apps extension: card-bearing tools + their ui:// resources (docs/DESIGN.md §14)
    farm_status.register(apps, registry, source)
    sale.register(apps, registry, source)
    briefing.register_cards(apps, registry, source, ai)
    health.register_cards(apps, registry, source, ai)
    server = MCPServer(
        name=APP_NAME,
        title=APP_NAME,
        instructions=f"{APP_NAME} is a voice farm manager for poultry farmers. Call get_help to see what it can do.",
        version="0.1.0",
        middleware=[guard],
        extensions=[apps],
    )
    feed.register(server, registry, source)
    profile.register(server, registry, source)
    contract_terms.register(server, registry, source)
    records.register(server, registry, source)
    health.register(server, registry, source)
    follow_up.register(server, registry, source)
    help_tool.register(server, registry)
    guard.bind(server)
    return server


def _json_error(status: int, message: str) -> tuple[int, bytes]:
    body = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": message}}
    return status, json.dumps(body).encode("utf-8")


async def _send(send: Send, status: int, body: bytes, extra_headers: list[tuple[bytes, bytes]] | None = None) -> None:
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers + (extra_headers or [])})
    await send({"type": "http.response.body", "body": body})


class ProtocolVersionGate:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            version = Headers(scope=scope).get(MCP_PROTOCOL_VERSION_HEADER)
            if version is not None and version not in HANDSHAKE_PROTOCOL_VERSIONS:
                logger.info("rejected MCP-Protocol-Version %r", version)
                status, body = _json_error(
                    400, f"Unsupported MCP-Protocol-Version. This server uses {TARGET_PROTOCOL_VERSION} via initialize."
                )
                await _send(send, status, body)
                return
        await self.app(scope, receive, send)


INVALID_REQUEST_MESSAGE = "Invalid request: not a JSON-RPC 2.0 request."  # protocol text, never farmer-facing
METHOD_NOT_FOUND_MESSAGE = "Method not found"
PARSE_ERROR_MESSAGE = "Parse error"  # the JSON-RPC 2.0 standard names, with no library text
_INVALID_REQUEST, _METHOD_NOT_FOUND, _PARSE_ERROR = -32600, -32601, -32700  # the JSON-RPC 2.0 codes
_SDK_VALIDATION_CODE = -32602  # what the SDK answers (with pydantic's text) for a body that is not a request


def _scrub_protocol_error(status: int, payload: bytes) -> bytes:
    """The fixed answer for the two SDK errors that repeat the input or library text; ``payload`` unchanged for every
    other answer. Only an object with an ``error`` and no ``result`` is ever rewritten, so a tool result is never
    touched (a tool failure is a ``result`` with ``isError``)."""
    if status != 400 and str(_METHOD_NOT_FOUND).encode() not in payload:
        return payload  # the cheap test: nothing else is looked at, the common answer is not even parsed
    try:
        body = json.loads(payload)
    except ValueError:
        logger.warning("a JSON response of %d bytes (status %d) did not parse; sent unchanged", len(payload), status)
        return payload
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict) or "result" in body:
        return payload
    if (
        status == 400
        and error.get("code") == _SDK_VALIDATION_CODE
        and str(error.get("message", "")).startswith("Validation error")
    ):
        fixed = {"jsonrpc": "2.0", "id": None, "error": {"code": _INVALID_REQUEST, "message": INVALID_REQUEST_MESSAGE}}
    elif (
        status == 400 and error.get("code") == _PARSE_ERROR and str(error.get("message", "")).startswith("Parse error")
    ):
        fixed = {"jsonrpc": "2.0", "id": None, "error": {"code": _PARSE_ERROR, "message": PARSE_ERROR_MESSAGE}}
    elif error.get("code") == _METHOD_NOT_FOUND:
        request_id = body.get("id")
        fixed = {
            "jsonrpc": "2.0",
            "id": request_id if isinstance(request_id, (str, int)) else None,
            "error": {"code": _METHOD_NOT_FOUND, "message": METHOD_NOT_FOUND_MESSAGE},
        }
    else:
        return payload
    return json.dumps(fixed).encode("utf-8")


class ProtocolErrorGate:
    """Wraps the SDK app. A POST answered with JSON is held until complete, so the two SDK answers that echo the input
    or pydantic's text (F1 and F2 of Step 48B) can be replaced by a short fixed one; every other response, and every
    non-JSON one (an event stream), passes through as it is."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        held: Message | None = None
        body = bytearray()
        passthrough = False

        async def capture(message: Message) -> None:
            nonlocal held, passthrough
            if passthrough or (message["type"] != "http.response.start" and held is None):
                await send(message)
                return
            if message["type"] == "http.response.start":
                if Headers(raw=message.get("headers", [])).get("content-type", "").startswith("application/json"):
                    held = message
                else:
                    passthrough = True
                    await send(message)
                return
            body.extend(message.get("body", b""))
            if message.get("more_body", False):
                return
            assert held is not None
            payload = _scrub_protocol_error(held["status"], bytes(body))
            headers = [(k, v) for k, v in held.get("headers", []) if k.lower() != b"content-length"]
            headers.append((b"content-length", str(len(payload)).encode()))
            await send({**held, "headers": headers})
            await send({"type": "http.response.body", "body": payload})

        await self.app(scope, receive, capture)


class BearerAuth:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            given = (Headers(scope=scope).get("authorization") or "").encode()
            if not hmac.compare_digest(given, self._expected):
                status, body = _json_error(401, "Missing or invalid bearer token.")
                await _send(send, status, body, [(b"www-authenticate", b"Bearer")])
                return
        await self.app(scope, receive, send)


class CorsForAllowedOrigins:
    """CORS for the explicitly allowed extra origins only (CLUCKTALK_ALLOWED_ORIGINS), for a browser-based MCP
    Apps host. Outermost layer, so a preflight (which carries no Authorization header) is answered before the
    bearer and Origin checks. Any other Origin passes through untouched: the transport's Origin check still
    answers it (403) and no CORS header is added. The allowed origin is echoed exactly, never ``*``, and there is
    no credentials mode."""

    METHODS = b"POST, GET, DELETE, OPTIONS"
    ALLOW_HEADERS = b"content-type, accept, authorization, mcp-session-id, mcp-protocol-version"
    EXPOSE_HEADERS = b"Mcp-Session-Id"

    def __init__(self, app: ASGIApp, origins: tuple[str, ...]) -> None:
        self.app = app
        self._origins = frozenset(origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        origin = Headers(scope=scope).get("origin") if scope["type"] == "http" else None
        if origin is None or origin not in self._origins:
            await self.app(scope, receive, send)
            return
        allow_origin = [(b"access-control-allow-origin", origin.encode()), (b"vary", b"Origin")]
        if scope["method"] == "OPTIONS" and Headers(scope=scope).get("access-control-request-method"):
            headers = [
                *allow_origin,
                (b"access-control-allow-methods", self.METHODS),
                (b"access-control-allow-headers", self.ALLOW_HEADERS),
                (b"access-control-max-age", b"600"),
            ]
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message: dict) -> None:
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        *allow_origin,
                        (b"access-control-expose-headers", self.EXPOSE_HEADERS),
                    ],
                }
            await send(message)

        await self.app(scope, receive, send_with_cors)


def _transport_security(settings: Settings) -> TransportSecuritySettings:
    names = _LOCAL_HOST_NAMES if settings.is_local else (settings.host,)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{n}:{settings.port}" for n in names],
        allowed_origins=list(settings.allowed_origins),
    )


def build_app(settings: Settings, server: MCPServer | None = None) -> ASGIApp:
    """ASGI app for ``settings``. Tests pass their own ``server`` (from build_mcp_server) to add probe tools."""
    server = server or build_mcp_server()
    app: ASGIApp = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=True,
        transport_security=_transport_security(settings),
        host=settings.host,
    )
    app = ProtocolErrorGate(app)
    app = ProtocolVersionGate(app)
    if settings.auth_token:
        app = BearerAuth(app, settings.auth_token)
    if settings.extra_origins:
        app = CorsForAllowedOrigins(app, settings.extra_origins)
    return app


def open_state_store(settings: Settings) -> SqliteStore:
    """The one state file this run uses: the demo-clock file when the demo clock is on (a separate file, marked as
    such), otherwise the live file. The live file is never opened while the clock is on."""
    return SqliteStore(settings.active_state_path, demo_clock=bool(settings.demo_days_later))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    import uvicorn

    try:
        store = open_state_store(settings)
    except (StoreError, sqlite3.Error, OSError) as exc:  # fail loud: never run without the farmer's saved state
        print(f"State store error ({settings.active_state_path}): {exc}", file=sys.stderr)
        return 2
    demo_clock = DemoClock(settings.demo_days_later) if settings.demo_days_later else None
    source = DemoFarmSource(store=store, demo_clock=demo_clock)
    try:  # the farmer's own weather rules: off unless the rules file exists (docs/DESIGN.md, Step 50W-B)
        source.weather = weather_from_env(os.environ, source.now)
    except WeatherConfigError as exc:
        print(f"Weather configuration error: {exc}", file=sys.stderr)
        return 2
    if settings.mock_bedrock:
        ai, mode = demo_ai(), "DEMO DATA (MOCK_BEDROCK=true), AI off (demo rules)"
    else:
        # Live AI on the synthetic demo farm: only on an explicit MOCK_BEDROCK=false + model + Region.
        try:
            ai = live_ai(settings, store, source.now)
        except ConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        mode = (
            f"DEMO FARM DATA + LIVE AI ({settings.bedrock_model_id}, {settings.aws_region}, "
            f"cap {settings.ai_max_calls_per_day} calls/day)"
        )
    server = build_mcp_server(source, ai)
    print(f"{APP_NAME} MCP server | mode: {mode} | protocol {TARGET_PROTOCOL_VERSION}")
    if demo_clock is not None:
        print(f"DEMO CLOCK: +{settings.demo_days_later} days (today and now are shifted; stored data is not changed)")
    print(f"Endpoint: http://{settings.host}:{settings.port}{MCP_PATH}")
    weather = getattr(source, "weather", None)
    if weather is None:
        print("Weather reminders: off (no rules file; nothing is asked of any weather service)")
    else:
        kind = "SIMULATED forecast" if isinstance(weather.port, MockForecast) else "live Open-Meteo forecast (opt-in)"
        print(f"Weather reminders: ON, {len(weather.config.rules)} rule(s) from the farmer's file, {kind}")
    print(f"Allowed browser origins: {', '.join(settings.allowed_origins)}")
    if settings.extra_origins:
        print(f"CORS enabled only for: {', '.join(settings.extra_origins)} (CLUCKTALK_ALLOWED_ORIGINS)")
    print(
        f"Farm state: {settings.active_state_path} "
        "(python tasks.py reset-demo --yes starts a fresh demo story; the live file is moved to backups)"
    )
    if demo_clock is not None:
        print("The live farm state file is not opened while the demo clock is on (a separate demo-clock file is used).")
    uvicorn.run(build_app(settings, server), host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
