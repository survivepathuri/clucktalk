"""get_farm_status and plan_feed over real HTTP (docs/DESIGN.md §5 tool contract, §6 behavior, §7 safety).
The demo farm is pinned to FIXED_DAY (a Tuesday). Expected story values come from data/seed/demo_farm.json
(House 2: 26 deaths today; 900 kg stock; simulated price ₹38.50/kg) or from definitions, never from tool output."""

from __future__ import annotations

import json
import statistics
import time

import jsonschema
import pytest

from tests.contract.test_tools import _assert_contract_error, _call, _tools
from tests.crossmodal import tool_output_problems

HOUSE_2_SYNONYMS = ["shed 2", "house two", "kotam do", "second shed", "Shed Two", "house-2"]
SCREEN_WORDS = ("screen", "card", "tap", "click", "see below", "shown")
SCREEN_WORDS_TE = ("స్క్రీన్", "కార్డు", "తెర")


def _ok(live, sid, name, args=None):
    body = _call(live, sid, name, args)
    result = body["result"]
    assert result.get("isError") in (None, False), result
    return result


def _schemas(live, sid):
    return {n: t["outputSchema"] for n, t in _tools(live, sid).items()}


CALLS = [
    ("get_farm_status", None),
    *[("get_farm_status", {"house": ref}) for ref in ("shed 1", "shed 2", "kotam 3")],
    ("plan_feed", None),
    *[("plan_feed", {"house": ref}) for ref in ("house 1", "house 2", "house 3")],
    *[("plan_feed", {"house": "shed 2", "horizon_days": h}) for h in (1, 7, 14)],
]


@pytest.mark.parametrize(("tool", "args"), CALLS)
def test_output_schema_voice_text_and_cross_modal(live, tool, args):
    sid, _ = live.initialize()
    result = _ok(live, sid, tool, args)
    sc = result["structuredContent"]
    jsonschema.validate(sc, _schemas(live, sid)[tool])
    assert [c["text"] for c in result["content"] if c["type"] == "text"] == [sc["text_en"]]
    assert sc["text_te"].strip() and sc["text_te"] != sc["text_en"]
    assert sc["demo_data"] is True
    # Spoken numbers must equal card numbers, scoped per finding / per house, and en == te (tests/crossmodal.py).
    assert tool_output_problems(sc) == []
    spoken = [sc["text_en"], sc["text_te"]]
    for item in sc.get("houses", []) + sc.get("plans", []):
        spoken += [item["summary_en"], item["summary_te"]]
        spoken += [t for f in item.get("findings", []) for t in (f["text_en"], f["text_te"])]
    for text in spoken:
        for word in SCREEN_WORDS + SCREEN_WORDS_TE:
            assert word not in text.lower(), f"voice text must not refer to a screen: {word!r} in {text!r}"


@pytest.mark.parametrize("ref", HOUSE_2_SYNONYMS)
def test_farmer_words_resolve_to_the_same_house(live, ref):
    sid, _ = live.initialize()
    status = _ok(live, sid, "get_farm_status", {"house": ref})["structuredContent"]
    plan = _ok(live, sid, "plan_feed", {"house": ref})["structuredContent"]
    assert [h["house_id"] for h in status["houses"]] == ["house-2"]
    assert [p["house_id"] for p in plan["plans"]] == ["house-2"]


def test_house_id_chains_from_status_to_plan(live):
    sid, _ = live.initialize()
    ids = [h["house_id"] for h in _ok(live, sid, "get_farm_status")["structuredContent"]["houses"]]
    assert sorted(ids) == ["house-1", "house-2", "house-3"]
    for hid in ids:
        assert _ok(live, sid, "plan_feed", {"house": hid})["structuredContent"]["plans"][0]["house_id"] == hid


def test_demo_story_house_2_alert(live):
    sid, _ = live.initialize()
    sc = _ok(live, sid, "get_farm_status")["structuredContent"]
    assert sc["level"] == "alert"
    worst = sc["houses"][0]
    assert worst["house_id"] == "house-2" and worst["level"] == "alert"
    spike = next(f for f in worst["findings"] if f["code"] == "mortality_spike")
    assert spike["values"]["deaths"] == 26
    assert "26 birds died today" in sc["text_en"]
    assert "vet" in sc["text_en"], "a mortality spike must carry the check-birds / call-vet step"


def test_feed_plan_cost_is_bags_times_price_and_labeled_simulated(live):
    sid, _ = live.initialize()
    sc = _ok(live, sid, "plan_feed", {"house": "shed 2"})["structuredContent"]
    p = sc["plans"][0]
    assert p["stock_kg"] == 900 and p["reorder_needed"] is True
    assert p["suggested_order_kg"] == p["suggested_order_bags"] * p["bag_kg"] == p["suggested_order_bags"] * 50
    assert p["feed_price_per_kg_inr"] == 38.5 and p["price_is_simulated"] is True
    assert p["suggested_order_cost_inr"] == round(p["suggested_order_kg"] * 38.5)
    assert "simulated" in sc["text_en"] and "అంచనా ధర (డెమో)" in sc["text_te"]
    assert len(p["daily"]) == p["horizon_days"] == 7
    assert p["need_kg"] == round(sum(d["feed_kg"] for d in p["daily"]))


def test_feed_plan_never_claims_an_order_was_placed(live):
    sid, _ = live.initialize()
    text = _ok(live, sid, "plan_feed", {"house": "shed 2"})["structuredContent"]["text_en"].lower()
    for claim in ("ordered", "order placed", "placed an order", "i have ordered", "confirmed"):
        assert claim not in text


def test_unknown_house_is_a_contract_error_that_lists_real_sheds(live):
    sid, _ = live.initialize()
    for tool in ("get_farm_status", "plan_feed"):
        result = _call(live, sid, tool, {"house": "shed 9"})["result"]
        _assert_contract_error(result)
        err = result["_meta"]["clucktalk/error"]
        assert "House 1, House 2, House 3" in err["next_step_en"]
        assert "house-" not in json.dumps(err), "stable IDs are for tools, not for speech"


@pytest.mark.parametrize("horizon", [0, 15, "seven"])
def test_horizon_outside_declared_range_is_a_contract_error(live, horizon):
    sid, _ = live.initialize()
    _assert_contract_error(_call(live, sid, "plan_feed", {"house": "shed 2", "horizon_days": horizon})["result"])


def test_tools_declare_farmer_synonyms_and_limits(live):
    sid, _ = live.initialize()
    tools = _tools(live, sid)
    for name in ("get_farm_status", "plan_feed"):
        house = tools[name]["inputSchema"]["properties"]["house"]
        assert all(w in house["description"] for w in ("shed", "kotam", "house"))
        assert tools[name]["annotations"]["readOnlyHint"] is True
    horizon = tools["plan_feed"]["inputSchema"]["properties"]["horizon_days"]
    assert (horizon["minimum"], horizon["maximum"], horizon["default"]) == (1, 14, 7)
    assert "dana" in tools["plan_feed"]["description"]


def test_help_lists_the_farm_tools(live):
    sid, _ = live.initialize()
    caps = _ok(live, sid, "get_help")["structuredContent"]["capabilities"]
    assert [c["tool_name"] for c in caps] == [
        "get_farm_status",
        "plan_sale",
        "plan_feed",
        "set_farm_mode",
        "set_contract_terms",
        "get_record_book",
        "log_daily_record",
        "start_health_check",
        "prepare_vet_handoff",
    ]


@pytest.mark.parametrize(("tool", "args"), [("get_farm_status", None), ("plan_feed", None)])
def test_latency_p95_under_500ms(live, tool, args):
    sid, _ = live.initialize()
    samples = []
    for _ in range(40):
        t0 = time.perf_counter()
        _ok(live, sid, tool, args)
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"\n{tool} (all houses) HTTP round trip: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=40)")
    assert p95 < 500


def test_spoken_weekday_is_the_last_covered_day(live):
    """Definition: stock covering d full days from tomorrow lasts 'until' as_of + d (FIXED_DAY is a Tuesday)."""
    from datetime import date, timedelta

    from clucktalk.server.render import weekday_en, weekday_te

    sid, _ = live.initialize()
    sc = _ok(live, sid, "plan_feed", {"house": "shed 2"})["structuredContent"]
    p, as_of = sc["plans"][0], date.fromisoformat(sc["as_of"])
    assert as_of.weekday() == 1 and 1 <= p["days_covered"] <= 6
    last = as_of + timedelta(days=p["days_covered"])
    assert f"until {weekday_en(last)}" in sc["text_en"]
    assert f"{weekday_te(last)} వరకు" in sc["text_te"]
