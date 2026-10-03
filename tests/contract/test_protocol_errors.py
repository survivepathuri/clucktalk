"""Step 48C part B: the SDK's two protocol-level answers that echoed input or library text (findings F1 and F2 of
Step 48B) are now a short fixed JSON-RPC error. F1: a body that is JSON but not a JSON-RPC request. F2: an unknown
method name. Neither answer repeats the input or says anything the pydantic library wrote; no tool result changes."""

from __future__ import annotations

import json
import re

import pytest

from tests.contract.test_fuzz_inputs import BIG, RAW_BODIES, Rig, rig  # noqa: F401  (rig is the module fixture)

INVALID_REQUEST = {
    "jsonrpc": "2.0",
    "id": None,
    "error": {"code": -32600, "message": "Invalid request: not a JSON-RPC 2.0 request."},
}
LIBRARY_TEXT = re.compile(
    r"pydantic|errors\.pydantic\.dev|validation error|ValidationError|Traceback|File \"|site-packages|\.py\"|"
    r"input_value|input_type|union\[",
    re.I,
)
MARK = "ZZ_MARKER_9f3a"
NOT_A_REQUEST = {
    "null": b"null",
    "number": b"42",
    "string": json.dumps(MARK).encode(),
    "empty list": b"[]",
    "batch": json.dumps([{"jsonrpc": "2.0", "id": 1, "method": MARK}]).encode(),
    "no method": json.dumps({"jsonrpc": "2.0", "id": 1, MARK: MARK}).encode(),
    "wrong version": json.dumps({"jsonrpc": "1.0", "id": 1, "method": "ping", "x": MARK}).encode(),
    "params of the wrong type": json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": MARK}).encode(),
    "method of the wrong type": json.dumps({"jsonrpc": "2.0", "id": 1, "method": [MARK]}).encode(),
}


@pytest.mark.parametrize("name", list(NOT_A_REQUEST))
def test_a_body_that_is_not_a_request_gets_one_short_fixed_error(rig: Rig, name: str):  # noqa: F811
    before = rig.state()
    r = rig.post_raw(NOT_A_REQUEST[name])
    assert r.status_code == 400, (name, r.status_code, r.text[:200])
    assert r.json() == INVALID_REQUEST
    assert MARK not in r.text and not LIBRARY_TEXT.search(r.text)
    assert len(r.content) < 200
    assert rig.state() == before


def test_an_unknown_method_gets_the_standard_error_without_the_method_name(rig: Rig):  # noqa: F811
    before = rig.state()
    r = rig.call("no/such/method", rid=11)
    assert r.json() == {"jsonrpc": "2.0", "id": 11, "error": {"code": -32601, "message": "Method not found"}}
    assert "no/such/method" not in r.text
    assert rig.state() == before


def test_a_one_megabyte_method_name_gets_a_small_answer(rig: Rig):  # noqa: F811
    before = rig.state()
    r = rig.post_raw(RAW_BODIES["huge method"])
    assert len(RAW_BODIES["huge method"]) > 1_000_000 and len(r.content) < 200, len(r.content)
    assert r.json()["error"] == {"code": -32601, "message": "Method not found"}
    assert BIG[:50] not in r.text
    assert rig.state() == before
    rig.healthy()


def test_no_library_text_in_any_known_body_of_these_two_families(rig: Rig):  # noqa: F811
    for name, body in {**RAW_BODIES, **NOT_A_REQUEST}.items():
        r = rig.post_raw(body)
        try:
            error = r.json()["error"]
        except (ValueError, KeyError, TypeError):
            continue
        if error.get("code") in (-32600, -32601, -32602) and r.status_code in (200, 400):
            if error.get("message", "").startswith("Parse error"):
                continue  # not part of F1 or F2 (invalid JSON text), left as it is
            assert not LIBRARY_TEXT.search(r.text), (name, r.text[:200])


def test_the_other_errors_are_left_alone(rig: Rig):  # noqa: F811
    # a tool's own error result and an unknown tool name still come back as the tool layer made them
    r = rig.call("tools/call", {"name": "no_such_tool", "arguments": {}}, rid=21).json()
    assert r["id"] == 21 and ("result" in r or "error" in r)
    ok = rig.call("tools/call", {"name": "get_help", "arguments": {}}, rid=22).json()
    assert ok["id"] == 22 and ok["result"]["content"] and "error" not in ok
    listed = rig.call("tools/list", rid=23).json()
    assert listed["result"]["tools"]


def test_a_non_json_body_keeps_the_sdk_parse_error_status(rig: Rig):  # noqa: F811
    r = rig.post_raw(b"{")
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700


def test_the_server_stays_healthy_after_these_requests(rig: Rig):  # noqa: F811
    for body in NOT_A_REQUEST.values():
        rig.post_raw(body)
    rig.healthy()
