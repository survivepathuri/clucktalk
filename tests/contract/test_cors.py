"""CORS for an explicitly allowed browser origin (the MCP Apps host test), docs/DESIGN.md §4.

The Origin check stays strict: only the server's own loopback origins plus what CLUCKTALK_ALLOWED_ORIGINS lists.
CORS headers are sent only for those extra origins, never `*`, never with credentials."""

from __future__ import annotations

import httpx2
import pytest

from tests.contract.conftest import _start
from tests.contract.test_transport import PING

EXTRA = "http://localhost:8080"
CORS_HEADER_PREFIX = "access-control-"
PREFLIGHT = {
    "access-control-request-method": "POST",
    "access-control-request-headers": "content-type, accept, mcp-session-id, mcp-protocol-version",
}


@pytest.fixture(scope="module")
def cors_live():
    srv, stop = _start({"CLUCKTALK_ALLOWED_ORIGINS": EXTRA})
    yield srv
    stop()


@pytest.fixture(scope="module")
def cors_live_with_token():
    srv, stop = _start({"CLUCKTALK_ALLOWED_ORIGINS": EXTRA, "CLUCKTALK_AUTH_TOKEN": "s3cret-test-token"})
    yield srv, "s3cret-test-token"
    stop()


def _cors(headers: httpx2.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower().startswith(CORS_HEADER_PREFIX)}


def _preflight(srv, origin: str, **extra: str) -> httpx2.Response:
    return httpx2.options(srv.url, headers={"origin": origin, **PREFLIGHT, **extra}, timeout=10)


def test_preflight_from_an_allowed_origin_is_204_with_exact_headers(cors_live):
    r = _preflight(cors_live, EXTRA)
    assert r.status_code == 204
    assert r.headers["access-control-allow-origin"] == EXTRA  # the exact origin, never *
    assert "origin" in r.headers["vary"].lower()
    assert r.headers["access-control-allow-methods"] == "POST, GET, DELETE, OPTIONS"
    allowed = {h.strip().lower() for h in r.headers["access-control-allow-headers"].split(",")}
    assert allowed == {"content-type", "accept", "authorization", "mcp-session-id", "mcp-protocol-version"}
    assert "access-control-allow-credentials" not in r.headers
    assert "*" not in " ".join(r.headers.values())


def test_actual_response_to_an_allowed_origin_exposes_the_session_id(cors_live):
    r = cors_live.post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        },
        origin=EXTRA,
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == EXTRA
    assert r.headers["access-control-expose-headers"] == "Mcp-Session-Id"
    assert "origin" in r.headers["vary"].lower()
    assert r.headers["mcp-session-id"]  # the header the browser host must be able to read
    assert "access-control-allow-credentials" not in r.headers


def test_a_disallowed_origin_is_403_with_no_cors_headers(cors_live):
    sid, _ = cors_live.initialize()
    r = cors_live.post(PING, session_id=sid, origin="http://evil.example")
    assert r.status_code == 403
    assert _cors(r.headers) == {}


def test_a_preflight_from_a_disallowed_origin_gets_no_cors_headers(cors_live):
    r = _preflight(cors_live, "http://evil.example")
    assert r.status_code != 204
    assert _cors(r.headers) == {}


def test_the_extra_origin_is_added_to_the_default_ones_not_a_replacement(cors_live):
    sid, _ = cors_live.initialize()
    own = cors_live.post(PING, session_id=sid, origin=f"http://localhost:{cors_live.port}")
    assert own.status_code == 200
    assert _cors(own.headers) == {}  # own loopback origins pass the check but get no CORS headers


def test_default_config_sends_no_cors_headers_and_rejects_the_extra_origin(live):
    sid, _ = live.initialize()
    own = live.post(PING, session_id=sid, origin=f"http://127.0.0.1:{live.port}")
    assert own.status_code == 200 and _cors(own.headers) == {}
    assert live.post(PING, session_id=sid, origin=EXTRA).status_code == 403
    assert _cors(_preflight(live, EXTRA).headers) == {}
    assert _cors(_preflight(live, f"http://localhost:{live.port}").headers) == {}


def test_a_request_without_an_origin_gets_no_cors_headers(cors_live):
    r = httpx2.post(cors_live.url, json=PING, headers=cors_live.headers(), timeout=10)
    assert _cors(r.headers) == {}


def test_the_preflight_is_answered_before_the_bearer_check(cors_live_with_token):
    srv, token = cors_live_with_token
    assert _preflight(srv, EXTRA).status_code == 204  # a preflight never carries the Authorization header
    r = httpx2.post(srv.url, json=PING, headers={**srv.headers(), "origin": EXTRA, "authorization": ""}, timeout=10)
    assert r.status_code == 401  # the real request still needs the token
