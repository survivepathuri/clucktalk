"""Tool contract: tools/list shape, get_help output, error contract, latency (docs/DESIGN.md §3, §5, §6)."""

from __future__ import annotations

import json
import statistics
import time

import jsonschema

from clucktalk.config import APP_NAME
from tests.contract.conftest import LEAK_SECRET

REQUIRED_ERROR_FIELDS = {"message_en", "message_te", "next_step_en", "next_step_te"}


def _tools(live, sid):
    return {t["name"]: t for t in live.call(sid, "tools/list")["result"]["tools"]}


def _call(live, sid, name, arguments=None):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return live.call(sid, "tools/call", params)


def _assert_contract_error(result):
    """Rule 4: isError, one safe sentence + next step, bilingual structured error, nothing internal."""
    assert result["isError"] is True
    # Spec 2025-11-25: structured results MUST match outputSchema, so errors carry none; details go in _meta.
    assert "structuredContent" not in result
    err = result["_meta"]["clucktalk/error"]
    assert set(err) == REQUIRED_ERROR_FIELDS
    assert all(isinstance(v, str) and v.strip() for v in err.values())
    spoken = " ".join(c["text"] for c in result["content"] if c["type"] == "text")
    assert spoken == f"{err['message_en']} {err['next_step_en']}"
    wire = json.dumps(result)
    for forbidden in (LEAK_SECRET, "Traceback", "RuntimeError", "validation error", "Error executing tool"):
        assert forbidden not in wire
    for tool_name in ("get_help", "crash_probe"):
        assert tool_name not in spoken


def test_every_tool_declares_title_description_and_output_schema(live):
    sid, _ = live.initialize()
    tools = _tools(live, sid)
    assert "get_help" in tools
    for t in tools.values():
        assert t.get("title") and len(t.get("description", "")) >= 40
        assert t["inputSchema"]["type"] == "object"
        jsonschema.validators.validator_for(t["outputSchema"]).check_schema(t["outputSchema"])


def test_get_help_output_matches_schema_and_is_cross_modal(live):
    sid, _ = live.initialize()
    schema = _tools(live, sid)["get_help"]["outputSchema"]
    result = _call(live, sid, "get_help")["result"]
    assert result.get("isError") in (None, False)
    sc = result["structuredContent"]
    jsonschema.validate(sc, schema)
    spoken = [c["text"] for c in result["content"] if c["type"] == "text"]
    assert spoken == [sc["text_en"]], "voice text must be exactly the structured English text"
    assert sc["text_te"].strip() and sc["text_te"] != sc["text_en"]
    assert APP_NAME in sc["text_en"]


def test_get_help_lists_only_registered_tools(live):
    sid, _ = live.initialize()
    names = set(_tools(live, sid))
    caps = _call(live, sid, "get_help")["result"]["structuredContent"]["capabilities"]
    assert {c["tool_name"] for c in caps} <= names - {"get_help"}


def test_bad_arguments_give_contract_error(live):
    sid, _ = live.initialize()
    _assert_contract_error(_call(live, sid, "get_help", arguments="not-an-object")["result"])


def test_crash_gives_generic_contract_error_without_leaking(live_with_probe):
    sid, _ = live_with_probe.initialize()
    _assert_contract_error(_call(live_with_probe, sid, "crash_probe")["result"])


def test_unknown_tool_does_not_leak_internals(live):
    sid, _ = live.initialize()
    body = live.call(sid, "tools/call", {"name": "no_such_tool"})
    if "result" in body:
        _assert_contract_error(body["result"])
    else:  # a JSON-RPC protocol error is also valid here; it must stay generic
        assert "Traceback" not in json.dumps(body)


def test_get_help_latency_p95_under_500ms(live):
    """Rule 4 budget, measured over real HTTP round trips on localhost."""
    sid, _ = live.initialize()
    samples = []
    for _ in range(60):
        t0 = time.perf_counter()
        _call(live, sid, "get_help")
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"\nget_help HTTP round trip: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=60)")
    assert p95 < 500


def test_no_2026_fields_on_the_2025_11_25_wire(live_with_probe):
    """2025-11-25 results have no resultType (added in 2026-07-28), on success and on every error path."""
    sid, _ = live_with_probe.initialize()
    bodies = [
        _call(live_with_probe, sid, "get_help"),
        _call(live_with_probe, sid, "get_help", arguments="not-an-object"),
        _call(live_with_probe, sid, "crash_probe"),
    ]
    for body in bodies:
        assert "resultType" not in body["result"], body
