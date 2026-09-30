"""plan_sale / set_contract_terms over real HTTP (docs/DESIGN.md §12.4, §5.1, §6). Demo story (FIXED_DAY, a
Tuesday): House 3 is broiler, day 43, on target, with 3 days of rising mortality -> plan_sale says sell now."""

from __future__ import annotations

import json
import statistics
import time

import jsonschema
import pytest

from tests.contract.test_farm_tools import SCREEN_WORDS, SCREEN_WORDS_TE
from tests.contract.test_tools import _assert_contract_error, _call, _tools
from tests.crossmodal import spoken_numbers, unbacked_numbers

MONEY_WORDS = ("₹",)


def _ok(live, sid, name, args=None, schemas=None):
    result = _call(live, sid, name, args)["result"]
    assert result.get("isError") in (None, False), result
    sc = result["structuredContent"]
    assert [c["text"] for c in result["content"] if c["type"] == "text"] == [sc["text_en"]]
    assert sc["text_te"].strip() and sc["text_te"] != sc["text_en"]
    if schemas is not None:
        jsonschema.validate(sc, schemas[name])
    for text in (sc["text_en"], sc["text_te"]):
        for word in SCREEN_WORDS + SCREEN_WORDS_TE:
            assert word not in text.lower(), f"voice text must not refer to a screen: {word!r} in {text!r}"
        assert "prop_" not in text, "proposal IDs are for tools, never spoken"
    assert unbacked_numbers(sc, sc["text_en"], sc["text_te"]) == []
    assert sorted(spoken_numbers(sc["text_en"], set())) == sorted(spoken_numbers(sc["text_te"], set()))
    return sc


def _session(live):
    sid, _ = live.initialize()
    return sid, {n: t["outputSchema"] for n, t in _tools(live, sid).items()}


def test_tools_declare_the_two_call_pattern_and_synonyms(live):
    sid, _ = live.initialize()
    tools = _tools(live, sid)
    sale, terms = tools["plan_sale"], tools["set_contract_terms"]
    assert sale["annotations"]["readOnlyHint"] is True
    assert terms["annotations"]["readOnlyHint"] is False and terms["annotations"]["idempotentHint"] is True
    for word in ("haan", "avunu", "own"):
        assert word in terms["description"]
    assert set(terms["inputSchema"]["required"]) == {
        "base_rate_per_kg",
        "standard_fcr",
        "incentive_per_kg_per_fcr_point",
        "deduction_per_kg_per_fcr_point",
    }
    # The field was saved but never used, so it is gone from the schema and the description (honesty fix).
    assert "mortality_allowance_pct" not in terms["inputSchema"]["properties"]
    assert "mortality" not in terms["description"].lower() and "four numbers" in terms["description"]


def test_house_three_says_sell_now_with_the_rising_mortality_reason(live):
    sid, schemas = _session(live)
    sc = _ok(live, sid, "plan_sale", {"house": "shed 3"}, schemas)
    assert len(sc["plans"]) == 1 and sc["unavailable"] == []
    h = sc["plans"][0]
    assert h["farm_mode"] == "independent" and h["weight_basis"] == "house_actual"
    assert h["mortality_rising"] is True
    assert h["best_day_index"] == 0 and h["break_even_day_index"] == 1
    assert "selling today is best" in sc["text_en"] == h["text_en"]  # single house: top text is the house's own
    assert h["days"][0]["in_days"] == 0 and h["days"][1]["in_days"] == 1
    assert h["price_is_simulated"] is True and h["live_price_per_kg_inr"] == 95.0


def test_house_one_says_wait_with_a_positive_difference(live):
    sid, schemas = _session(live)
    sc = _ok(live, sid, "plan_sale", {"house": "house one"}, schemas)
    h = sc["plans"][0]
    assert h["best_day_index"] > 0
    best = h["days"][h["best_day_index"]]
    assert best["net_vs_today_inr"] > 0
    assert "best to sell" in sc["text_en"]


def test_farmer_given_rate_overrides_the_simulated_price(live):
    sid, schemas = _session(live)
    sc = _ok(live, sid, "plan_sale", {"house": "shed 1", "live_price_per_kg": 120}, schemas)
    h = sc["plans"][0]
    assert h["price_is_simulated"] is False and h["live_price_per_kg_inr"] == 120.0


def test_whole_farm_lists_broiler_sheds_worst_break_even_first(live):
    sid, schemas = _session(live)
    sc = _ok(live, sid, "plan_sale", None, schemas)
    assert len(sc["plans"]) == 3  # all three demo houses are broilers now (broiler-first)
    assert sc["plans"][0]["house_id"] == "house-3"  # the one with a break-even day, spoken first


def test_layer_specific_wording_never_appears(live):
    sid, _ = live.initialize()
    tools = _tools(live, sid)
    assert "laying" not in tools["get_farm_status"]["description"].lower()


def test_unknown_house_and_bad_horizon_are_contract_errors(live):
    sid, _ = live.initialize()
    result = _call(live, sid, "plan_sale", {"house": "shed nine"})["result"]
    _assert_contract_error(result)


def test_negative_price_is_a_contract_error(live):
    sid, _ = live.initialize()
    result = _call(live, sid, "plan_sale", {"house": "shed 1", "live_price_per_kg": -5})["result"]
    _assert_contract_error(result)


@pytest.mark.parametrize("tool", ["plan_sale"])
def test_latency_p95_under_500ms(live, tool):
    sid, _ = live.initialize()
    samples = []
    for _ in range(40):
        t0 = time.perf_counter()
        _ok(live, sid, tool, None)
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"\n{tool} (all houses) HTTP round trip: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=40)")
    assert p95 < 500


# ---------------------------------------------------------------------------------------------------------------
# Contract mode: FCR + growing charge, and set_contract_terms itself follows the one confirmation pattern.
# ---------------------------------------------------------------------------------------------------------------
def _switch_to_contract(live, sid):
    pid = _ok(live, sid, "set_farm_mode", {"mode": "contract"})["proposal_id"]
    _ok(live, sid, "set_farm_mode", {"mode": "contract", "proposal_id": pid, "answer": "yes"})


def test_contract_mode_shows_fcr_only_until_terms_are_saved(fresh):
    live = fresh.live
    sid, schemas = _session(live)
    _switch_to_contract(live, sid)
    sc = _ok(live, sid, "plan_sale", {"house": "shed 3"}, schemas)
    h = sc["plans"][0]
    assert h["farm_mode"] == "contract" and h["has_contract_terms"] is False
    assert h["live_price_per_kg_inr"] is None
    assert all(d["growing_charge_inr"] is None for d in h["days"])
    assert "set_contract_terms" in sc["text_en"]
    for word in MONEY_WORDS:
        assert word not in sc["text_en"]


def test_contract_mode_never_carries_a_market_price_number_even_unread(fresh):
    """Independent review 2026-09-29 (High): contract-mode structuredContent must never carry a market-price-
    derived rupee figure, even one nothing currently speaks or shows -- a contract farmer isn't paid that rate,
    and a future card/host reading the raw result could otherwise surface it as if it were real."""
    live = fresh.live
    sid, schemas = _session(live)
    _switch_to_contract(live, sid)
    sc = _ok(live, sid, "plan_sale", {"house": "shed 3"}, schemas)
    h = sc["plans"][0]
    assert h["best_day_index"] is None and h["break_even_day_index"] is None
    assert h["feed_price_per_kg_inr"] is None
    for d in h["days"]:
        assert d["gain_value_inr"] is None
        assert d["feed_cost_inr"] is None
        assert d["mortality_loss_inr"] is None
        assert d["marginal_profit_inr"] is None
        assert d["net_vs_today_inr"] is None
        # fcr and weight still compute: they don't depend on a market price.
        assert d["weight_g"] is not None and (d["fcr"] is None or isinstance(d["fcr"], float))


def test_set_contract_terms_needs_a_yes_then_plan_sale_shows_the_growing_charge(fresh):
    live = fresh.live
    sid, schemas = _session(live)
    _switch_to_contract(live, sid)
    args = {
        "base_rate_per_kg": 92,
        "standard_fcr": 1.85,
        "incentive_per_kg_per_fcr_point": 2,
        "deduction_per_kg_per_fcr_point": 3,
    }
    first = _ok(live, sid, "set_contract_terms", args, schemas)
    assert first["status"] == "needs_confirmation" and first["terms"] is None
    assert first["proposed"]["base_rate_per_kg_inr"] == 92.0
    # Nothing changed yet.
    assert _ok(live, sid, "plan_sale", {"house": "shed 3"})["plans"][0]["has_contract_terms"] is False

    done = _ok(live, sid, "set_contract_terms", {**args, "proposal_id": first["proposal_id"], "answer": "yes"}, schemas)
    assert done["status"] == "changed" and done["terms"]["base_rate_per_kg_inr"] == 92.0

    sc = _ok(live, sid, "plan_sale", {"house": "shed 3"}, schemas)
    h = sc["plans"][0]
    assert h["has_contract_terms"] is True
    assert h["days"][0]["growing_charge_inr"] is not None
    assert "growing charge" in sc["text_en"] and "supervisor" in sc["text_en"]


FOUR_TERMS = {
    "base_rate_per_kg": 92,
    "standard_fcr": 1.85,
    "incentive_per_kg_per_fcr_point": 2,
    "deduction_per_kg_per_fcr_point": 3,
}


def test_the_read_back_speaks_exactly_four_numbers_and_no_mortality_allowance(fresh):
    live = fresh.live
    sid, schemas = _session(live)
    _switch_to_contract(live, sid)
    first = _ok(live, sid, "set_contract_terms", FOUR_TERMS, schemas)
    assert "mortality" not in first["text_en"].lower()
    assert sorted(first["proposed"]) == [
        "base_rate_per_kg_inr",
        "deduction_per_kg_per_fcr_point_inr",
        "incentive_per_kg_per_fcr_point_inr",
        "standard_fcr",
        "updated_at",
    ]
    # 92, 1.85, 2, 3 and the 0.1 FCR step: nothing else is spoken as a figure.
    assert sorted(spoken_numbers(first["text_en"], set())) == [0.1, 0.1, 1.85, 2.0, 3.0, 92.0]


def test_the_retired_mortality_allowance_is_refused_not_silently_ignored(fresh):
    live = fresh.live
    sid, _ = _session(live)
    _switch_to_contract(live, sid)
    result = _call(live, sid, "set_contract_terms", {**FOUR_TERMS, "mortality_allowance_pct": 5})["result"]
    _assert_contract_error(result)
    assert "mortality_allowance_pct" not in json.dumps(result)  # the next step does not echo caller data
    # Nothing was proposed or saved by the refused call.
    assert _ok(live, sid, "plan_sale", {"house": "shed 3"})["plans"][0]["has_contract_terms"] is False


def test_repeating_the_same_terms_yes_never_saves_twice(fresh):
    live = fresh.live
    sid, _ = _session(live)
    _switch_to_contract(live, sid)
    args = {
        "base_rate_per_kg": 92,
        "standard_fcr": 1.85,
        "incentive_per_kg_per_fcr_point": 2,
        "deduction_per_kg_per_fcr_point": 3,
    }
    pid = _ok(live, sid, "set_contract_terms", args)["proposal_id"]
    confirm_args = {**args, "proposal_id": pid, "answer": "yes"}
    first = _ok(live, sid, "set_contract_terms", confirm_args)
    again = _ok(live, sid, "set_contract_terms", confirm_args)
    assert first["replayed"] is False and again["replayed"] is True
    assert first["terms"]["updated_at"] == again["terms"]["updated_at"]


def test_no_keeps_no_terms_saved(fresh):
    live = fresh.live
    sid, _ = _session(live)
    _switch_to_contract(live, sid)
    args = {
        "base_rate_per_kg": 92,
        "standard_fcr": 1.85,
        "incentive_per_kg_per_fcr_point": 2,
        "deduction_per_kg_per_fcr_point": 3,
    }
    pid = _ok(live, sid, "set_contract_terms", args)["proposal_id"]
    out = _ok(live, sid, "set_contract_terms", {**args, "proposal_id": pid, "answer": "no"})
    assert out["status"] == "cancelled" and out["terms"] is None


def test_malformed_terms_request_is_a_contract_error(fresh):
    live = fresh.live
    sid, _ = _session(live)
    result = _call(live, sid, "set_contract_terms", {"base_rate_per_kg": -1, "standard_fcr": 1.8,
                    "incentive_per_kg_per_fcr_point": 2,
                    "deduction_per_kg_per_fcr_point": 3})["result"]  # fmt: skip
    _assert_contract_error(result)


def test_help_lists_plan_sale_and_set_contract_terms(live):
    sid, _ = live.initialize()
    caps = _ok(live, sid, "get_help")["capabilities"]
    names = [c["tool_name"] for c in caps]
    assert "plan_sale" in names and "set_contract_terms" in names
    assert json.dumps(caps).count("prop_") == 0
