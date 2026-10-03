"""Protocol conformance, pinned as observed (Step 48A, docs/DESIGN.md §4).

These tests record what the server does TODAY on the wire. They do not say the behaviour is right for Alexa+.
Where a test is named ``..._pinned_finding`` the behaviour looks questionable for Alexa+ and is reported for a
decision; changing the server must change that test on purpose."""

from __future__ import annotations

import json
import socket
from typing import Any

import httpx2
import pytest

from clucktalk.server.app import TARGET_PROTOCOL_VERSION
from tests.contract.conftest import LiveServer, _start
from tests.contract.test_transport import PING

BOTH = "application/json, text/event-stream"
LIST_TOOLS = {"jsonrpc": "2.0", "id": 9, "method": "tools/list"}
SUPPORTED_SINCE_2024 = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def _initialize_body(version: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": {"name": "conformance", "version": "0"},
        },
    }


def _post(live: LiveServer, body: dict[str, Any], headers: dict[str, str]) -> httpx2.Response:
    return httpx2.post(live.url, json=body, headers={"content-type": "application/json", **headers}, timeout=10)


def _post_without_accept_header(live: LiveServer, body: dict[str, Any]) -> tuple[int, bytes]:
    """A raw HTTP request that carries no Accept header at all (httpx2 would add ``Accept: */*``)."""
    payload = json.dumps(body).encode()
    head = (
        f"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{live.port}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
    ).encode()
    with socket.create_connection(("127.0.0.1", live.port), timeout=10) as s:
        s.sendall(head + payload)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    status_line, _, rest = data.partition(b"\r\n")
    return int(status_line.split()[1]), rest.partition(b"\r\n\r\n")[2]


# (1) initialize with each protocol version ------------------------------------------------------------------


@pytest.mark.parametrize("version", SUPPORTED_SINCE_2024)
def test_initialize_answers_with_the_clients_own_version_for_every_handshake_version_pinned_finding(
    live: LiveServer, version: str
):
    """FINDING: the server agrees to the CLIENT's version when it is one the SDK knows, including 2024-11-05, 2025-03-26
    and 2025-06-18, which are older than 2025-11-25. It does not answer with its own newest version. The Alexa+
    track's stated minimum is 2025-11-25 (Step 48A brief); whether Alexa+ would refuse a lower answer is not
    verified. Only the version a client asks for decides the answer."""
    r = _post(live, _initialize_body(version), {"accept": BOTH})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["protocolVersion"] == version


@pytest.mark.parametrize("version", ["1999-01-01", "2026-07-28", "not-a-version"])
def test_initialize_with_a_version_the_sdk_does_not_know_answers_with_the_servers_own(live: LiveServer, version: str):
    """Not an error: an unknown or newer (stateless) version in the initialize BODY is answered with 2025-11-25."""
    r = _post(live, _initialize_body(version), {"accept": BOTH})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["protocolVersion"] == TARGET_PROTOCOL_VERSION


def test_a_2024_11_05_session_keeps_working_and_is_not_forced_up(live: LiveServer):
    sid, body = live.initialize("2024-11-05")
    assert body["result"]["protocolVersion"] == "2024-11-05"
    r = _post(live, LIST_TOOLS, {"accept": BOTH, "mcp-session-id": sid, "mcp-protocol-version": "2024-11-05"})
    assert r.status_code == 200
    assert r.json()["result"]["tools"]


def test_a_protocol_header_that_differs_from_the_negotiated_version_is_not_checked_pinned_finding(live: LiveServer):
    """FINDING: on a 2025-11-25 session, a request that sends ``MCP-Protocol-Version: 2024-11-05`` is accepted,
    and so is a request with no protocol header. The spec says the header must match the negotiated version."""
    sid, _ = live.initialize()
    base = {"accept": BOTH, "mcp-session-id": sid}
    assert _post(live, LIST_TOOLS, {**base, "mcp-protocol-version": "2024-11-05"}).status_code == 200
    assert _post(live, LIST_TOOLS, base).status_code == 200


# (2) Accept header variants on POST, and GET on /mcp -------------------------------------------------------


@pytest.mark.parametrize(
    ("accept", "status"),
    [
        (BOTH, 200),
        ("application/json", 200),
        ("*/*", 200),
        ("text/event-stream", 406),
    ],
)
def test_post_accept_variants(live: LiveServer, accept: str, status: int):
    r = _post(live, _initialize_body(TARGET_PROTOCOL_VERSION), {"accept": accept})
    assert r.status_code == status, r.text
    if status == 200:
        assert r.headers["content-type"].startswith("application/json")  # a JSON reply, never an event stream
    else:
        assert "must accept application/json" in r.json()["error"]["message"]


def test_post_with_no_accept_header_at_all_is_406(live: LiveServer):
    """The MCP spec says a client MUST send Accept; the server enforces it (httpx2 hides this by adding */*)."""
    status, body = _post_without_accept_header(live, _initialize_body(TARGET_PROTOCOL_VERSION))
    assert status == 406
    assert "Not Acceptable" in json.loads(body)["error"]["message"]


def test_post_with_a_non_json_content_type_is_400(live: LiveServer):
    r = httpx2.post(
        live.url,
        content=json.dumps(_initialize_body(TARGET_PROTOCOL_VERSION)),
        headers={"content-type": "text/plain", "accept": BOTH},
        timeout=10,
    )
    assert r.status_code == 400


def test_get_without_a_session_is_400_even_with_an_event_stream_accept(live: LiveServer):
    r = httpx2.get(live.url, headers={"accept": "text/event-stream"}, timeout=10)
    assert r.status_code == 400
    assert "session" in r.json()["error"]["message"].lower()


def test_get_that_does_not_accept_an_event_stream_is_406_even_with_a_valid_session(live: LiveServer):
    sid, _ = live.initialize()
    r = httpx2.get(live.url, headers=live.headers(sid, accept="application/json"), timeout=10)
    assert r.status_code == 406
    assert "text/event-stream" in r.json()["error"]["message"]


# (3) DELETE on /mcp -----------------------------------------------------------------------------------------


def test_delete_without_a_session_id_is_400(live: LiveServer):
    r = httpx2.delete(live.url, timeout=10)
    assert r.status_code == 400
    assert "session" in r.json()["error"]["message"].lower()


def test_delete_with_an_unknown_session_id_is_404(live: LiveServer):
    r = httpx2.delete(live.url, headers={"mcp-session-id": "0" * 32}, timeout=10)
    assert r.status_code == 404


def test_delete_with_a_real_session_ends_it_once(live: LiveServer):
    sid, _ = live.initialize()
    first = httpx2.delete(live.url, headers=live.headers(sid), timeout=10)
    assert first.status_code == 200
    assert httpx2.delete(live.url, headers=live.headers(sid), timeout=10).status_code == 404
    assert live.post(PING, session_id=sid).status_code == 404


# (4) unknown or missing session id on a non-initialize request ----------------------------------------------


def test_a_request_with_no_session_id_is_400(live: LiveServer):
    r = _post(live, LIST_TOOLS, {"accept": BOTH})
    assert r.status_code == 400
    assert "session" in r.json()["error"]["message"].lower()


@pytest.mark.parametrize("session_id", ["x" * 32, "", "not-a-session"])
def test_a_request_with_an_unknown_or_empty_session_id_is_404(live: LiveServer, session_id: str):
    r = _post(live, LIST_TOOLS, {"accept": BOTH, "mcp-session-id": session_id})
    assert r.status_code == 404
    assert r.json()["error"]["message"] == "Session not found"


def test_the_error_body_for_a_bad_session_is_json_rpc_with_a_null_id(live: LiveServer):
    r = _post(live, LIST_TOOLS, {"accept": BOTH, "mcp-session-id": "y" * 32})
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] is None
    assert body["error"]["code"] == -32600


# (5) exact-origin and CORS ----------------------------------------------------------------------------------


def _cors_headers(r: httpx2.Response) -> dict[str, str]:
    return {k: v for k, v in r.headers.items() if k.lower().startswith("access-control-")}


def test_a_disallowed_origin_is_403_with_no_cors_headers_on_post_get_delete_and_preflight(live: LiveServer):
    sid, _ = live.initialize()
    evil = "http://evil.example"
    responses = [
        _post(live, _initialize_body(TARGET_PROTOCOL_VERSION), {"accept": BOTH, "origin": evil}),
        httpx2.get(live.url, headers=live.headers(sid, accept="text/event-stream", origin=evil), timeout=10),
        httpx2.delete(live.url, headers=live.headers(sid, origin=evil), timeout=10),
        httpx2.options(live.url, headers={"origin": evil, "access-control-request-method": "POST"}, timeout=10),
    ]
    for r in responses:
        assert r.status_code == 403, (r.request.method, r.text)
        assert _cors_headers(r) == {}, r.request.method


def test_the_origin_match_is_exact_not_a_prefix_or_a_port_wildcard(live: LiveServer):
    sid, _ = live.initialize()
    own = f"http://localhost:{live.port}"
    for origin in (f"{own}.evil.example", f"{own}/", f"https://localhost:{live.port}", "null"):
        assert live.post(PING, session_id=sid, origin=origin).status_code == 403, origin
    assert live.post(PING, session_id=sid, origin=own).status_code == 200


def test_an_allowed_loopback_origin_gets_no_cors_headers_when_none_are_configured(live: LiveServer):
    """CORS headers are for the explicitly configured extra origins only (tests/contract/test_cors.py)."""
    sid, _ = live.initialize()
    r = live.post(PING, session_id=sid, origin=f"http://localhost:{live.port}")
    assert r.status_code == 200
    assert _cors_headers(r) == {}


def test_a_disallowed_origin_is_403_with_no_cors_headers_when_cors_is_configured():
    srv, stop = _start({"CLUCKTALK_ALLOWED_ORIGINS": "http://localhost:8080"})
    try:
        r = _post(srv, _initialize_body(TARGET_PROTOCOL_VERSION), {"accept": BOTH, "origin": "http://evil.example"})
        assert r.status_code == 403
        assert _cors_headers(r) == {}
    finally:
        stop()
