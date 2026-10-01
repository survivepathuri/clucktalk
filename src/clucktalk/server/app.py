"""Server factory and entry point (docs/DESIGN.md §2-§4).

Layers, outermost first:
1. ``BearerAuth``: when CLUCKTALK_AUTH_TOKEN is set (required off-localhost by config), every request
   must carry ``Authorization: Bearer <token>``.
2. ``ProtocolVersionGate``: only initialize-handshake protocol versions reach the SDK. The SDK would route a
   2026-07-28 header to its stateless path; CluckTalk targets 2025-11-25 (docs/VERSIONS.md).
3. SDK Streamable HTTP app with explicit Host/Origin allow-lists (DNS-rebinding protection) and sessions.

Run (Windows):  python tasks.py serve
"""

from __future__ import annotations

import hmac
import json
import logging
import sqlite3
import sys

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http import MCP_PROTOCOL_VERSION_HEADER
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, LATEST_HANDSHAKE_VERSION
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

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
    app = ProtocolVersionGate(app)
    if settings.auth_token:
        app = BearerAuth(app, settings.auth_token)
    if settings.extra_origins:
        app = CorsForAllowedOrigins(app, settings.extra_origins)
    return app


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    import uvicorn

    try:
        store = SqliteStore(settings.state_path)
    except (StoreError, sqlite3.Error, OSError) as exc:  # fail loud: never run without the farmer's saved state
        print(f"State store error ({settings.state_path}): {exc}", file=sys.stderr)
        return 2
    demo_clock = DemoClock(settings.demo_days_later) if settings.demo_days_later else None
    source = DemoFarmSource(store=store, demo_clock=demo_clock)
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
    print(f"Allowed browser origins: {', '.join(settings.allowed_origins)}")
    if settings.extra_origins:
        print(f"CORS enabled only for: {', '.join(settings.extra_origins)} (CLUCKTALK_ALLOWED_ORIGINS)")
    print(f"Farm state: {settings.state_path} (python tasks.py reset-demo restores the demo story)")
    uvicorn.run(build_app(settings, server), host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
