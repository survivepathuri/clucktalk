"""Daily Briefing over real HTTP (docs/DESIGN.md §6, §18): ``get_daily_briefing``.

The tool only reads: it computes the facts from the record book in microseconds, orders them by rules, and applies
a stored AI ordering when one is ready. The model runs on the slow path (``ManualRunner`` here, so each test drives
it and can see the "still preparing" state). FIXED_DAY = 2026-09-29: House 2 has the seeded death spike."""

from __future__ import annotations

import json
import re
import statistics
import time
from datetime import datetime, timedelta
from datetime import time as dtime

import jsonschema
import pytest

from clucktalk.agents import AiServices
from clucktalk.agents.budget import AiBudget
from clucktalk.agents.model import RulesModel
from clucktalk.agents.runner import ManualRunner
from clucktalk.domain.profile import FarmMode, FarmProfile
from clucktalk.server.farm_state import IST, DemoFarmSource
from tests.contract.conftest import FIXED_DAY, Clock, _start
from tests.contract.test_card import APP_MIME, EXTERNAL
from tests.contract.test_farm_tools import SCREEN_WORDS, SCREEN_WORDS_TE
from tests.contract.test_health_tools import ATTACK, Rig, _assert_no_treatment_advice, _rig
from tests.contract.test_record_tools import DayClock
from tests.contract.test_tools import _tools
from tests.crossmodal import spoken_numbers, unbacked_numbers
from tests.fakes import FIXTURES, RepeatingModel, ScriptedModel

TOOL = "get_daily_briefing"


def _brief(rig: Rig, **args):
    result = rig.call(TOOL, **args)
    assert result.get("isError") in (None, False), result
    sc = result["structuredContent"]
    assert [c["text"] for c in result["content"] if c["type"] == "text"] == [sc["text_en"]]
    assert sc["demo_data"] is True and sc["text_te"].strip() and sc["text_te"] != sc["text_en"]
    for text in (sc["text_en"], sc["text_te"]):
        for word in SCREEN_WORDS + SCREEN_WORDS_TE:
            assert word not in text.lower(), f"voice text must not refer to a screen: {word!r} in {text!r}"
    assert unbacked_numbers(sc, sc["text_en"], sc["text_te"]) == []
    assert sorted(spoken_numbers(sc["text_en"], set())) == sorted(spoken_numbers(sc["text_te"], set()))
    _assert_no_treatment_advice(result)
    assert len(sc["items"]) <= 5
    return sc


def _ids(sc):
    return [i["fact_id"] for i in sc["items"]]


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


@pytest.fixture
def rig_reversing():
    """A model that reverses whatever list it is given (it may only pick from the ids it is offered)."""
    yield from _rig(FIXTURES["rank_reversed"]())


@pytest.fixture
def make_rig():
    """Builds a rig around any model; every server is stopped at teardown."""
    gens = []

    def make(model) -> Rig:
        gen = _rig(model)
        gens.append(gen)
        return next(gen)

    yield make
    for gen in gens:
        next(gen, None)


def _stamp_urgent_checks(rig: Rig, houses=("shed one", "shed two", "shed three")):
    for h in houses:
        rig.call("start_health_check", house=h, signs=["swollen_head"])
    rig.runner.run_all()


# -- the tool --------------------------------------------------------------------------------------------------------
def test_tool_is_listed_read_only_with_a_card_and_one_optional_argument(rig):
    tools = {t["name"]: t for t in rig.live.call(rig.sid, "tools/list")["result"]["tools"]}
    tool = tools[TOOL]
    assert tool["annotations"]["readOnlyHint"] is True and tool["annotations"]["idempotentHint"] is True
    assert tool["_meta"]["ui"]["resourceUri"] == "ui://clucktalk/briefing.html"
    props = tool["inputSchema"]["properties"]
    assert set(props) == {"more"} and props["more"]["type"] == "boolean"
    assert "required" not in tool["inputSchema"] or not tool["inputSchema"]["required"]
    desc = tool["description"].lower()
    assert "briefing" in desc and "more" in desc


def test_the_demo_story_puts_the_spike_first_and_reads_out_three(rig):
    sc = _brief(rig)
    schema = _tools(rig.live, rig.sid)[TOOL]["outputSchema"]
    jsonschema.validate(sc, schema)
    first = sc["items"][0]
    assert first["fact_id"] == "mortality_spike:house-2" and first["pinned"] is True and first["level"] == "alert"
    assert first["rank"] == 1 and first["number"] == 2 and "26 birds died today" in first["text_en"]
    assert len(sc["items"]) >= 4 and sc["total_items"] >= len(sc["items"])
    assert [i["spoken"] for i in sc["items"]] == [True, True, True] + [False] * (len(sc["items"]) - 3)
    assert sc["more_available"] is True
    for spoken in sc["items"][:3]:
        assert spoken["text_en"] in sc["text_en"]
    assert sc["items"][3]["text_en"] not in sc["text_en"]
    assert "more" in sc["text_en"].lower() and sc["as_of"] == FIXED_DAY.isoformat()
    assert "call your vet if deaths continue" in sc["text_en"]  # a spoken death spike ends with the safe next step
    assert sc["level"] == "alert"
    assert sc["ai"]["engine"] == "rules" and sc["ai"]["note"] is None


def test_more_reads_the_rest_and_not_the_first_three_again(rig):
    first = _brief(rig)
    rest = _brief(rig, more=True)
    assert _ids(rest) == _ids(first)  # the card and the ranking do not change
    for i in first["items"][:3]:
        assert i["text_en"] not in rest["text_en"]
    for i in first["items"][3:]:
        assert i["text_en"] in rest["text_en"]
    assert [i["spoken"] for i in rest["items"]] == [False] * 3 + [True] * (len(rest["items"]) - 3)
    assert rest["more_available"] is False


def test_health_alerts_always_come_first_and_the_list_is_capped_at_five(rig):
    _stamp_urgent_checks(rig)
    sc = _brief(rig)
    assert len(sc["items"]) == 5 and sc["total_items"] > 5
    # House 2's check is a suspected reportable disease (red flag + the record-book spike): outranks the rest.
    assert sc["items"][0]["fact_id"] == "open_health_check:house-2"
    pinned = [i["pinned"] for i in sc["items"]]
    assert pinned == sorted(pinned, reverse=True)  # every pinned item sits before every unpinned one
    assert sum(pinned) >= 4  # spike + three open checks
    assert "not a diagnosis" in sc["text_en"]  # a triage result is spoken: its disclaimer is too


def test_every_item_is_bilingual_and_carries_its_numbers(rig):
    sc = _brief(rig)
    for i in sc["items"]:
        assert i["text_en"].strip() and i["text_te"].strip() and i["text_te"] != i["text_en"]
        assert i["level"] in ("alert", "watch", "info")
        assert isinstance(i["values"], dict) and isinstance(i["simulated"], bool)
        for v in i["values"].values():  # whole numbers are ints on the wire (26, not 26.0)
            assert not (isinstance(v, float) and v.is_integer()), i["values"]
    reminder = next((i for i in sc["items"] if i["category"] == "not_logged_today"), None)
    if reminder is not None:
        assert reminder["level"] == "info" and reminder["house_id"] is None


# -- the card ---------------------------------------------------------------------------------------------------
def test_the_carousel_card_is_a_self_contained_mcp_app_resource(rig):
    uri = "ui://clucktalk/briefing.html"
    listed = rig.live.call(rig.sid, "resources/list")["result"]["resources"]
    assert any(r["uri"] == uri and r["mimeType"] == APP_MIME for r in listed)
    (content,) = rig.live.call(rig.sid, "resources/read", {"uri": uri})["result"]["contents"]
    html = content["text"]
    assert content["mimeType"] == APP_MIME and html.startswith("<!doctype html>")
    assert not any(p.search(html) for p in EXTERNAL)  # nothing is fetched: the host's default CSP allows none
    assert '"@SERVER_DEMO@"' not in html and "aria-roledescription" in html and "data:font/otf;base64," in html
    assert content["_meta"]["ui"].get("prefersBorder") is False or "prefersBorder" not in content["_meta"]["ui"]


# -- three days later ------------------------------------------------------------------------------------------------
def _dated_rig():
    day_clock = DayClock(FIXED_DAY)
    source = DemoFarmSource(clock=day_clock, now=lambda: datetime.combine(day_clock.day, dtime(10, 0), tzinfo=IST))
    runner = ManualRunner()
    srv, stop = _start({}, source=source, ai=AiServices(RulesModel(), None, runner))
    sid, _ = srv.initialize()
    return Rig(srv, source, runner, RulesModel(), sid), day_clock, stop


def _log(rig: Rig, **args):
    pid = rig.call("log_daily_record", **args)["structuredContent"]["proposal_id"]
    rig.call("log_daily_record", **args, proposal_id=pid, answer="yes")


def test_three_days_later_the_briefing_still_recalls_the_logged_spike():
    rig, day_clock, stop = _dated_rig()
    try:
        farm, _ = rig.source.snapshot()
        house1 = next(h for h in farm.houses if h.number == 1)
        spike = house1.records[-1].deaths + 500  # far outside any natural daily count
        _log(rig, house="shed 1", deaths=spike)

        today = _brief(rig)
        f = next(i for i in today["items"] if i["house_id"] == "house-1" and i["pinned"])
        assert f["category"] == "mortality_spike" and str(spike) in f["text_en"].replace(",", "")

        day_clock.day += timedelta(days=3)
        later = _brief(rig)
        recall = next(i for i in later["items"] if i["category"] == "recent_logged_spike")
        assert recall["house_id"] == "house-1" and recall["pinned"] is True and recall["level"] == "alert"
        assert recall["values"]["days_ago"] == 3 and recall["values"]["deaths"] == spike
        assert "3 days ago" in recall["text_en"] and str(spike) in recall["text_en"].replace(",", "")
        assert not any(i["category"] == "mortality_spike" and i["house_id"] == "house-1" for i in later["items"])
        assert later["as_of"] == (FIXED_DAY + timedelta(days=3)).isoformat()

        day_clock.day += timedelta(days=5)  # eight days on: outside the trailing week
        gone = _brief(rig)["items"]  # (the seeded demo farm has its own recent spikes on other houses)
        assert not any(i["category"] == "recent_logged_spike" and i["house_id"] == "house-1" for i in gone)
    finally:
        stop()


# -- the sale item ---------------------------------------------------------------------------------------------------
def test_a_sale_item_is_simulated_carries_no_money_and_only_appears_in_the_window(rig):
    sc = _brief(rig, more=True)
    sale = [i for i in sc["items"] if i["category"] == "sale_window"]
    for i in sale:
        assert i["simulated"] is True and i["pinned"] is False and "imulated" in i["text_en"]
        assert (
            "₹" not in i["text_en"] and "₹" not in i["text_te"] and set(i["values"]) == {"best_day_index", "best_day"}
        )
    everything = json.dumps(sc)
    assert ("sale_window" in everything) == bool(sale)


def test_the_sale_item_is_the_same_in_contract_mode_and_never_shows_a_rupee_figure(rig):
    rig.source.store.save_profile(FarmProfile(rig.source.farm_id, FarmMode.CONTRACT, "farmer", rig.source.now()))
    sc = _brief(rig, more=True)
    assert "₹" not in json.dumps(sc, ensure_ascii=False)


# -- the AI ordering: slow path, closed list, code floor -------------------------------------------------------------
def test_the_tool_never_waits_for_the_model_and_the_first_answer_is_the_rules_order(rig_reversing):
    rig = rig_reversing
    sc = _brief(rig)
    assert rig.model.requests == [] and rig.runner.pending == 1  # queued, not run
    assert sc["ai"]["engine"] == "rules" and sc["ai"]["note"] == "in_progress"
    assert "preparing" in sc["ai"]["label_en"].lower()


def test_a_ready_ai_ordering_reorders_only_the_unpinned_items(rig_reversing):
    rig = rig_reversing
    rules = _brief(rig, more=True)
    assert rig.runner.run_all() == 1
    ai = _brief(rig, more=True)
    assert ai["ai"]["engine"] == "scripted" and ai["ai"]["note"] is None
    assert ai["ai"]["model_id"] == "scripted-test-model"
    pinned = [i["fact_id"] for i in rules["items"] if i["pinned"]]
    assert [i["fact_id"] for i in ai["items"] if i["pinned"]] == pinned  # health: untouched, still first
    assert _ids(ai)[: len(pinned)] == pinned
    offered = rig.model.requests[-1].schema["properties"]["order"]["items"]["enum"]
    assert not set(offered) & set(pinned)  # the model was never offered a health item
    assert ai["total_items"] == rules["total_items"]  # nothing added or dropped
    rest_ai = [i for i in _ids(ai) if i not in pinned]
    assert rest_ai == list(reversed(offered))[: len(rest_ai)]  # the model's (reversed) order took effect
    assert rig.runner.pending == 0  # a ready ranking is served, not recomputed
    assert rig.source.store.count_ai_calls(rig.source.now().date(), "briefing") == 1


def test_writing_a_record_makes_the_ranking_stale_and_it_is_prepared_again(rig_reversing):
    rig = rig_reversing
    _brief(rig)
    rig.runner.run_all()
    assert rig.runner.pending == 0
    _log(rig, house="shed 3", deaths=1)
    sc = _brief(rig)
    assert sc["ai"]["note"] == "in_progress" and rig.runner.pending == 1
    _brief(rig)
    assert rig.runner.pending == 1  # debounced: one job, not one per call


def test_the_prompt_holds_only_ids_and_numbers_even_after_a_prompt_injection_check(rig_reversing):
    rig = rig_reversing
    rig.call("start_health_check", house="shed 1", signs=["coughing"], symptoms=ATTACK)
    rig.runner.run_all()  # triage job (the model reverses; irrelevant here)
    rig.model.requests.clear()
    _brief(rig)
    rig.runner.run_all()
    briefing_requests = [r for r in rig.model.requests if r.agent == "briefing"]
    assert briefing_requests, "the briefing job asked the model"
    for r in briefing_requests:
        text = r.system + r.user_text
        for banned in ("SYSTEM", "ignore all", "farmer_words", "ml"):
            assert banned not in r.user_text, banned
        assert list(r.schema["properties"]) == ["order"]  # no free-text output field exists
        assert "mortality_spike:house-2" not in r.user_text  # pinned health facts are never handed to the model
        assert text


@pytest.mark.parametrize(
    "bad",
    [{"order": ["mortality_spike:house-2"]}, {"order": ["made_up:house-9"]}, {"order": [], "note": "x"}, "text"],
)
def test_a_model_that_misbehaves_changes_nothing_and_says_so(make_rig, bad):
    rig = make_rig(RepeatingModel(bad))
    baseline = _ids(_brief(rig, more=True))
    rig.runner.run_all()
    sc = _brief(rig, more=True)
    assert _ids(sc) == baseline  # the rules order, exactly
    assert sc["ai"]["note"] == "no_answer" and sc["ai"]["engine"] == "rules"
    assert "didn't finish" in sc["ai"]["label_en"]
    assert sc["items"][0]["fact_id"] == "mortality_spike:house-2"
    ledger = rig.source.store.ai_calls(rig.source.now().date())
    assert [r["outcome"] for r in ledger if r["agent"] == "briefing"] == ["invalid_reply"] * 2


def test_a_model_outage_is_said_plainly_never_invented(make_rig):
    rig = make_rig(FIXTURES["always_fails"]())
    baseline = _ids(_brief(rig, more=True))
    rig.runner.run_all()
    sc = _brief(rig, more=True)
    assert _ids(sc) == baseline and sc["ai"]["note"] == "no_answer"
    ledger = rig.source.store.ai_calls(rig.source.now().date())
    assert [r["outcome"] for r in ledger if r["agent"] == "briefing"] == ["error"] * 2


def test_the_daily_limit_is_visible():
    clock = Clock()
    source = DemoFarmSource(clock=lambda: FIXED_DAY, now=clock)
    model = ScriptedModel()
    runner = ManualRunner()
    budget = AiBudget(source.store, clock, max_calls_per_day=0, min_interval_s=0)
    srv, stop = _start({}, source=source, ai=AiServices(model=model, budget=budget, runner=runner))
    try:
        sid, _ = srv.initialize()
        rig = Rig(srv, source, runner, model, sid)
        _brief(rig)
        runner.run_all()
        sc = _brief(rig)
        assert sc["ai"]["note"] == "daily_limit" and "limit" in sc["ai"]["label_en"].lower()
        assert model.requests == []
    finally:
        stop()


def test_demo_mode_labels_itself_and_never_queues_a_job(rig):
    sc = _brief(rig)
    assert rig.runner.pending == 0
    assert sc["ai"]["engine"] == "rules" and "no AI" in sc["ai"]["label_en"]


# -- latency (Rule 4) ------------------------------------------------------------------------------------------------
def test_briefing_latency_p95_under_500ms(rig):
    samples = []
    for _ in range(40):
        t0 = time.perf_counter()
        assert rig.call(TOOL)["structuredContent"]["items"]
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"\nget_daily_briefing HTTP round trip: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=40)")
    assert p95 < 500


def test_the_briefing_is_listed_in_help(rig):
    text = rig.call("get_help")["structuredContent"]["text_en"]
    assert "briefing" in text.lower()


def test_the_error_contract_holds_for_a_bad_argument(rig):
    result = rig.call(TOOL, more="perhaps")
    assert result["isError"] is True and re.search(r"\w", result["content"][0]["text"])
