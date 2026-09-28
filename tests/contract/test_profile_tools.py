"""get_farm_profile / set_farm_mode over real HTTP, and how the farm mode changes other answers
(docs/DESIGN.md §5.1 confirmation pattern, §13.1 farm profile). Each test gets a fresh server and store."""

from __future__ import annotations

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import jsonschema
import pytest

from clucktalk.domain.proposals import PROPOSAL_TTL
from tests.contract.test_farm_tools import SCREEN_WORDS, SCREEN_WORDS_TE
from tests.contract.test_tools import _assert_contract_error, _call, _tools
from tests.crossmodal import tool_output_problems

MONEY_WORDS = ("₹", "rupee", "price", "cost", "GST", "ధర")


def _ok(live, sid, name, args=None, schemas=None):
    result = _call(live, sid, name, args)["result"]
    assert result.get("isError") in (None, False), result
    sc = result["structuredContent"]
    assert [c["text"] for c in result["content"] if c["type"] == "text"] == [sc["text_en"]]
    assert sc["demo_data"] is True and sc["text_te"].strip() and sc["text_te"] != sc["text_en"]
    if schemas is not None:
        jsonschema.validate(sc, schemas[name])
    for text in (sc["text_en"], sc["text_te"]):
        for word in SCREEN_WORDS + SCREEN_WORDS_TE:
            assert word not in text.lower(), f"voice text must not refer to a screen: {word!r} in {text!r}"
        assert "prop_" not in text, "proposal IDs are for tools, never spoken"
    assert tool_output_problems(sc) == []
    return sc


def _session(fresh):
    sid, _ = fresh.live.initialize()
    return sid, {n: t["outputSchema"] for n, t in _tools(fresh.live, sid).items()}


def test_tools_declare_modes_synonyms_and_the_two_call_pattern(live):
    sid, _ = live.initialize()
    tools = _tools(live, sid)
    get, put = tools["get_farm_profile"], tools["set_farm_mode"]
    assert get["annotations"]["readOnlyHint"] is True and get["inputSchema"].get("properties", {}) == {}
    assert put["annotations"]["readOnlyHint"] is False and put["annotations"]["idempotentHint"] is True
    props = put["inputSchema"]["properties"]
    assert props["mode"]["enum"] == ["contract", "independent"] and put["inputSchema"]["required"] == ["mode"]
    assert {"yes", "no"} == set(next(s for s in props["answer"]["anyOf"] if "enum" in s)["enum"])
    assert next(s for s in props["proposal_id"]["anyOf"] if s.get("type") == "string")["pattern"]
    for word in ("integrator", "company", "own farm", "haan", "nahi", "two calls", "proposal_id"):
        assert word in put["description"], word


def test_demo_farm_starts_independent(fresh):
    sid, schemas = _session(fresh)
    sc = _ok(fresh.live, sid, "get_farm_profile", schemas=schemas)
    assert (sc["mode"], sc["set_by"], sc["updated_at"]) == ("independent", "demo_default", None)
    assert "independent farm" in sc["text_en"] and "switch to contract farming" in sc["text_en"]


def test_switch_needs_a_yes_then_changes_every_answer(fresh):
    live = fresh.live
    sid, schemas = _session(fresh)
    first = _ok(live, sid, "set_farm_mode", {"mode": "contract"}, schemas)
    assert first["status"] == "needs_confirmation" and first["proposal_id"].startswith("prop_")
    assert first["expires_in_minutes"] == 10 and first["mode_now"] == "independent"
    assert "Switch your farm to contract farming?" in first["text_en"] and "yes" in first["text_en"]
    # Nothing changed yet: the farm is still independent and plan_feed still prices the order.
    assert _ok(live, sid, "get_farm_profile")["mode"] == "independent"
    assert "simulated price" in _ok(live, sid, "plan_feed", {"house": "shed 2"})["text_en"]

    args = {"mode": "contract", "proposal_id": first["proposal_id"], "answer": "yes"}
    done = _ok(live, sid, "set_farm_mode", args, schemas)
    assert (done["status"], done["mode_now"], done["replayed"]) == ("changed", "contract", False)
    assert done["text_en"] == "Done. Your farm is now set up as a contract farm."
    profile = _ok(live, sid, "get_farm_profile", schemas=schemas)
    assert (profile["mode"], profile["set_by"]) == ("contract", "farmer") and profile["updated_at"]

    plan = _ok(live, sid, "plan_feed", {"house": "shed 2"}, schemas)
    p = plan["plans"][0]
    assert plan["farm_mode"] == "contract" and p["reorder_needed"] is True
    assert p["feed_price_per_kg_inr"] is None and p["suggested_order_cost_inr"] is None
    bags = p["suggested_order_bags"]
    assert f"Ask your supervisor for {bags} bags of 50 kg now." in plan["text_en"]
    assert f"సూపర్‌వైజర్‌ని 50 కిలోల {bags} బస్తాలు అడగండి" in plan["text_te"]
    for word in MONEY_WORDS:
        assert word.lower() not in (plan["text_en"] + plan["text_te"]).lower(), word
    farm_plan = _ok(live, sid, "plan_feed", None, schemas)
    assert "Ask your supervisor for" in farm_plan["text_en"] and "simulated cost" not in farm_plan["text_en"]
    status = _ok(live, sid, "get_farm_status", {"house": "shed 2"}, schemas)  # speaks its low-stock finding
    assert "how much feed to ask your supervisor for" in status["text_en"] and "to order" not in status["text_en"]


def test_repeating_the_same_yes_never_applies_twice(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    args = {"mode": "contract", "proposal_id": pid, "answer": "yes"}

    def send(i: int) -> dict:  # each in-flight request needs its own JSON-RPC id (FRICTION_LOG FL-011)
        body = live.call(sid, "tools/call", {"name": "set_farm_mode", "arguments": args}, rid=100 + i)
        assert body["result"].get("isError") in (None, False), body
        return body["result"]["structuredContent"]

    with ThreadPoolExecutor(max_workers=5) as pool:  # a host retrying the same "yes" at once
        results = list(pool.map(send, range(5)))
    assert sorted(r["replayed"] for r in results) == [False, True, True, True, True]
    assert all(r["status"] == "changed" and r["mode_now"] == "contract" for r in results)
    updated = _ok(live, sid, "get_farm_profile")["updated_at"]
    assert _ok(live, sid, "set_farm_mode", args)["replayed"] is True
    assert _ok(live, sid, "get_farm_profile")["updated_at"] == updated  # not re-applied


def test_no_keeps_the_farm_as_it_is(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    out = _ok(live, sid, "set_farm_mode", {"mode": "contract", "proposal_id": pid, "answer": "no"})
    assert (out["status"], out["mode_now"]) == ("cancelled", "independent")
    assert out["text_en"] == "Okay, nothing changed. Your farm stays an independent farm."
    assert _ok(live, sid, "get_farm_profile")["mode"] == "independent"


def test_a_late_yes_changes_nothing_and_asks_again(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    fresh.clock.t += PROPOSAL_TTL
    late = _ok(live, sid, "set_farm_mode", {"mode": "contract", "proposal_id": pid, "answer": "yes"})
    assert (late["status"], late["reason"], late["mode_now"]) == ("needs_confirmation", "expired", "independent")
    assert late["text_en"].startswith("That request timed out, so nothing changed. Switch your farm to contract")
    assert late["proposal_id"] != pid


def test_already_in_that_mode_asks_nothing(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    out = _ok(live, sid, "set_farm_mode", {"mode": "independent"})
    assert (out["status"], out["proposal_id"]) == ("already_set", None)
    assert out["text_en"] == "Your farm is already set up as an independent farm, so nothing changed."


def test_a_yes_for_something_else_changes_nothing(fresh):
    """The proposal was to switch to contract; a yes arriving with mode=independent must not apply it."""
    live = fresh.live
    sid, _ = _session(fresh)
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    out = _ok(live, sid, "set_farm_mode", {"mode": "independent", "proposal_id": pid, "answer": "yes"})
    assert (out["status"], out["reason"], out["mode_now"]) == ("cancelled", "changed", "independent")
    assert "different from what I read back" in out["text_en"]


def test_unknown_request_id_changes_nothing(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    args = {"mode": "contract", "proposal_id": "prop_0123456789abcdef", "answer": "yes"}
    out = _ok(live, sid, "set_farm_mode", args)
    assert (out["status"], out["reason"], out["mode_now"]) == ("needs_confirmation", "unknown", "independent")


@pytest.mark.parametrize(
    "args",
    [
        {"mode": "contract", "answer": "yes"},  # a yes with nothing to answer
        {"mode": "contract", "proposal_id": "prop_0123456789abcdef"},  # an ID without the farmer's answer
        {"mode": "contract", "proposal_id": "12345", "answer": "yes"},  # not a proposal ID
        {"mode": "contract", "proposal_id": "prop_0123456789abcdef", "answer": "maybe"},
        {"mode": "cooperative"},
        {},
    ],
)
def test_malformed_requests_are_contract_errors_and_change_nothing(fresh, args):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "set_farm_mode", args)["result"]
    _assert_contract_error(result)
    assert "prop_" not in json.dumps(result["_meta"])
    assert _ok(live, sid, "get_farm_profile")["mode"] == "independent"


def test_answer_without_request_says_what_happened(fresh):
    sid, _ = _session(fresh)
    err = _call(fresh.live, sid, "set_farm_mode", {"mode": "contract", "answer": "yes"})["result"]["_meta"]
    assert err["clucktalk/error"]["message_en"].startswith("There's nothing waiting for your yes or no")


@pytest.mark.parametrize(("tool", "args"), [("get_farm_profile", None), ("set_farm_mode", {"mode": "contract"})])
def test_latency_p95_under_500ms(fresh, tool, args):
    sid, _ = _session(fresh)
    samples = []
    for _ in range(40):
        t0 = time.perf_counter()
        _ok(fresh.live, sid, tool, args)
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"\n{tool} HTTP round trip: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=40)")
    assert p95 < 500


# Independent review 2026-09-28 (Rule 11) regressions.
def test_no_after_the_change_was_made_is_not_answered_with_done(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    _ok(live, sid, "set_farm_mode", {"mode": "contract", "proposal_id": pid, "answer": "yes"})
    late_no = _ok(live, sid, "set_farm_mode", {"mode": "contract", "proposal_id": pid, "answer": "no"})
    assert (late_no["status"], late_no["reason"], late_no["mode_now"]) == ("cancelled", "already_done", "contract")
    assert not late_no["text_en"].startswith("Done")
    assert "switch to independent farming" in late_no["text_en"]  # how to undo it


def test_the_latest_request_replaces_an_older_read_back(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    assert _ok(live, sid, "set_farm_mode", {"mode": "independent"})["status"] == "already_set"
    late = _ok(live, sid, "set_farm_mode", {"mode": "contract", "proposal_id": pid, "answer": "yes"})
    assert (late["status"], late["reason"], late["mode_now"]) == ("needs_confirmation", "superseded", "independent")


def test_contract_plan_flags_no_simulated_price(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    _ok(live, sid, "set_farm_mode", {"mode": "contract", "proposal_id": pid, "answer": "yes"})
    plan = _ok(live, sid, "plan_feed", None)
    assert all(p["price_is_simulated"] is False and p["feed_price_per_kg_inr"] is None for p in plan["plans"])
