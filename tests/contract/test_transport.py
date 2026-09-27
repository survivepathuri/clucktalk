"""Transport contract: protocol version, sessions, Origin/Host checks, auth (docs/DESIGN.md §4).
Expected status codes come from the MCP 2025-11-25 Streamable HTTP rules, not from observed output."""

from __future__ import annotations

import anyio
import httpx2
from mcp import Client

from clucktalk.config import APP_NAME
from clucktalk.server.app import TARGET_PROTOCOL_VERSION

PING = {"jsonrpc": "2.0", "id": 9, "method": "ping"}


def test_initialize_negotiates_2025_11_25_and_assigns_session(live):
    sid, body = live.initialize()
    result = body["result"]
    assert result["protocolVersion"] == TARGET_PROTOCOL_VERSION == "2025-11-25"
    assert result["serverInfo"]["name"] == APP_NAME
    assert "tools" in result["capabilities"]
    assert len(sid) >= 16


def test_sdk_client_in_auto_mode_lands_on_2025_11_25(live):
    """The SDK client probes the stateless 2026-07-28 protocol first; the gate must steer it to initialize."""

    async def connect() -> str:
        async with Client(live.url) as client:
            return client.protocol_version

    assert anyio.run(connect) == "2025-11-25"


def test_modern_protocol_header_is_rejected(live):
    r = live.post(PING, **{"mcp-protocol-version": "2026-07-28"})
    assert r.status_code == 400
    assert "2025-11-25" in r.json()["error"]["message"]


def test_request_without_session_after_init_is_rejected(live):
    live.initialize()
    r = live.post(PING)
    assert r.status_code == 400


def test_unknown_session_is_404(live):
    r = live.post(PING, session_id="0" * 32)
    assert r.status_code == 404


def test_deleted_session_is_404_afterwards(live):
    sid, _ = live.initialize()
    d = httpx2.delete(live.url, headers=live.headers(sid), timeout=10)
    assert d.status_code in (200, 204)
    assert live.post(PING, session_id=sid).status_code == 404


def test_foreign_origin_is_403(live):
    sid, _ = live.initialize()
    r = live.post(PING, session_id=sid, origin="http://evil.example")
    assert r.status_code == 403


def test_allowed_origin_passes(live):
    sid, _ = live.initialize()
    r = live.post(PING, session_id=sid, origin=f"http://localhost:{live.port}")
    assert r.status_code == 200


def test_other_localhost_port_origin_is_403(live):
    """The SDK default would allow any localhost port; CluckTalk uses an explicit allow-list."""
    sid, _ = live.initialize()
    r = live.post(PING, session_id=sid, origin="http://localhost:6666")
    assert r.status_code == 403


def test_foreign_host_header_is_421(live):
    sid, _ = live.initialize()
    r = live.post(PING, session_id=sid, host="attacker.example")
    assert r.status_code == 421


def test_token_required_when_configured(live_with_token):
    no_auth = httpx2.post(live_with_token.url, json=PING, headers={"content-type": "application/json"}, timeout=10)
    assert no_auth.status_code == 401
    wrong = httpx2.post(
        live_with_token.url,
        json=PING,
        headers={"content-type": "application/json", "authorization": "Bearer nope"},
        timeout=10,
    )
    assert wrong.status_code == 401
    sid, body = live_with_token.initialize()  # helper sends the right token
    assert body["result"]["protocolVersion"] == "2025-11-25"
