"""log_daily_record / get_record_book over real HTTP (docs/DESIGN.md §5.1 confirmation pattern, §13.4 record
book), and the farm_state.py seed-overlay integration that makes logged records the tools' data source.
Each test gets a fresh server and store (FIXED_DAY = 2026-09-29, a Tuesday)."""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime

import jsonschema
import pytest

from clucktalk.domain.proposals import PROPOSAL_TTL
from clucktalk.server.farm_state import IST, DemoFarmSource
from tests.contract.conftest import FIXED_DAY, _start
from tests.contract.test_farm_tools import SCREEN_WORDS, SCREEN_WORDS_TE
from tests.contract.test_tools import _assert_contract_error, _call, _tools
from tests.crossmodal import spoken_numbers, unbacked_numbers

DOSE_WORDS = ("dose", "ml", "mg", "cc")


class DayClock:
    """A test-only clock for a ``DemoFarmSource`` date argument: mutate ``.day`` to move "today" forward,
    the same way ``fresh.clock.t`` moves the wall clock for proposal expiry (tests/contract/conftest.py)."""

    def __init__(self, day: date) -> None:
        self.day = day

    def __call__(self) -> date:
        return self.day


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
    assert unbacked_numbers(sc, sc["text_en"], sc["text_te"]) == []
    assert sorted(spoken_numbers(sc["text_en"], set())) == sorted(spoken_numbers(sc["text_te"], set()))
    return sc


def _session(fresh):
    sid, _ = fresh.live.initialize()
    return sid, {n: t["outputSchema"] for n, t in _tools(fresh.live, sid).items()}


def test_tool_declares_the_fields_synonyms_and_two_call_pattern(live):
    sid, _ = live.initialize()
    tool = _tools(live, sid)["log_daily_record"]
    assert tool["annotations"]["readOnlyHint"] is False and tool["annotations"]["idempotentHint"] is True
    props = tool["inputSchema"]["properties"]
    assert tool["inputSchema"]["required"] == ["house"]
    assert {"yes", "no"} == set(next(s for s in props["answer"]["anyOf"] if "enum" in s)["enum"])
    assert next(s for s in props["proposal_id"]["anyOf"] if s.get("type") == "string")["pattern"]
    treatment_ref = props["treatments"]["anyOf"][0]["items"]["$ref"].rsplit("/", 1)[-1]
    treatment_kind = tool["inputSchema"]["$defs"][treatment_ref]["properties"]["kind"]["enum"]
    assert set(treatment_kind) == {"medicine", "vaccine"}
    assert "dose" not in tool["outputSchema"]["$defs"]["TreatmentOut"]["properties"]
    for word in ("mar gaye", "dana", "bori", "teeka", "dawai", "haan", "nahi", "dose", "two calls", "proposal_id"):
        assert word in tool["description"], word


def test_a_new_day_needs_a_yes_before_anything_is_saved(fresh):
    live = fresh.live
    sid, schemas = _session(fresh)
    args = {"house": "shed 2", "deaths": 3, "feed_bags": 2}
    first = _ok(live, sid, "log_daily_record", args, schemas)
    assert first["status"] == "needs_confirmation" and first["proposal_id"].startswith("prop_")
    assert first["expires_in_minutes"] == 10 and first["record"] is None
    assert first["proposed"]["deaths"] == 3 and first["proposed"]["feed_bags"] == 2
    assert "3 died" in first["text_en"] and "2 bags of feed" in first["text_en"]

    confirm_args = {**args, "proposal_id": first["proposal_id"], "answer": "yes"}
    done = _ok(live, sid, "log_daily_record", confirm_args, schemas)
    assert (done["status"], done["replayed"]) == ("changed", False)
    assert done["record"]["deaths"] == 3 and done["record"]["feed_bags"] == 2
    assert done["text_en"] == "Done. Saved for House 2, today."

    book = _ok(live, sid, "get_record_book")
    entry = next(e for e in book["entries"] if e["number"] == 2)
    assert entry["logged"] is True and entry["record"]["deaths"] == 3


def test_restating_the_same_values_needs_no_new_confirmation(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    args = {"house": "shed 2", "deaths": 3, "feed_bags": 2}
    pid = _ok(live, sid, "log_daily_record", args)["proposal_id"]
    _ok(live, sid, "log_daily_record", {**args, "proposal_id": pid, "answer": "yes"})

    repeat = _ok(live, sid, "log_daily_record", args)
    assert (repeat["status"], repeat["proposal_id"]) == ("already_set", None)
    assert "already has that recorded" in repeat["text_en"]


def test_a_correction_changes_only_the_field_given(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    first_args = {"house": "shed 2", "deaths": 5, "feed_bags": 2}
    pid = _ok(live, sid, "log_daily_record", first_args)["proposal_id"]
    _ok(live, sid, "log_daily_record", {**first_args, "proposal_id": pid, "answer": "yes"})

    correction = {"house": "shed 2", "deaths": 7}
    fix_pid = _ok(live, sid, "log_daily_record", correction)["proposal_id"]
    fixed = _ok(live, sid, "log_daily_record", {**correction, "proposal_id": fix_pid, "answer": "yes"})
    assert fixed["record"]["deaths"] == 7 and fixed["record"]["feed_bags"] == 2  # feed carried over
    assert "House 2 already has a record for today" not in fixed["text_en"]  # only spoken before the "yes"


def test_repeating_the_same_yes_never_applies_twice(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    args = {"house": "shed 2", "deaths": 3}
    pid = _ok(live, sid, "log_daily_record", args)["proposal_id"]
    confirm = {**args, "proposal_id": pid, "answer": "yes"}
    first = _ok(live, sid, "log_daily_record", confirm)
    second = _ok(live, sid, "log_daily_record", confirm)
    assert (first["replayed"], second["replayed"]) == (False, True)
    assert first["record"] == second["record"]


def test_no_keeps_nothing_saved(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    args = {"house": "shed 2", "deaths": 3}
    pid = _ok(live, sid, "log_daily_record", args)["proposal_id"]
    out = _ok(live, sid, "log_daily_record", {**args, "proposal_id": pid, "answer": "no"})
    assert out["status"] == "cancelled" and out["record"] is None


def test_a_weight_sample_needs_the_bird_count_too(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "log_daily_record", {"house": "shed 2", "avg_weight_g": 1850})["result"]
    _assert_contract_error(result)
    assert "how many birds were weighed" in result["_meta"]["clucktalk/error"]["message_en"]


def test_nothing_given_on_an_unlogged_day_is_a_domain_error(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "log_daily_record", {"house": "shed 2"})["result"]
    _assert_contract_error(result)
    assert "didn't catch anything to record" in result["_meta"]["clucktalk/error"]["message_en"]


def test_a_future_day_is_refused(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "log_daily_record", {"house": "shed 2", "deaths": 1, "day": "2026-09-30"})["result"]
    _assert_contract_error(result)
    assert "future" in result["_meta"]["clucktalk/error"]["message_en"]


def test_a_day_before_placement_is_refused(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "log_daily_record", {"house": "shed 2", "deaths": 1, "day": "2000-01-01"})["result"]
    _assert_contract_error(result)
    assert "wasn't placed yet" in result["_meta"]["clucktalk/error"]["message_en"]


def test_a_plain_iso_date_string_is_accepted_for_an_earlier_unlogged_day(fresh):
    live = fresh.live
    sid, schemas = _session(fresh)
    args = {"house": "shed 2", "day": "2026-09-27", "deaths": 2}
    out = _ok(live, sid, "log_daily_record", args, schemas)
    assert out["status"] == "needs_confirmation" and out["proposed"]["day"] == "2026-09-27"
    assert "on Sunday" in out["text_en"]


def test_a_medicine_or_vaccine_is_stored_by_name_only_never_a_dose(fresh):
    live = fresh.live
    sid, schemas = _session(fresh)
    args = {
        "house": "shed 2",
        "treatments": [{"kind": "vaccine", "name": "Newcastle"}, {"kind": "medicine", "name": "Amoxicillin"}],
    }
    out = _ok(live, sid, "log_daily_record", args, schemas)
    pid = out["proposal_id"]
    done = _ok(live, sid, "log_daily_record", {**args, "proposal_id": pid, "answer": "yes"})
    assert [t["name"] for t in done["record"]["treatments"]] == ["Newcastle", "Amoxicillin"]
    for text in (done["text_en"], done["text_te"], str(done["record"])):
        for word in DOSE_WORDS:
            assert not re.search(rf"\b{word}\b", text.lower()), f"a dose-shaped word leaked into: {text!r}"


def test_a_dose_in_the_treatment_name_is_rejected(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    args = {"house": "shed 1", "treatments": [{"kind": "vaccine", "name": "Newcastle 5ml"}]}
    result = _call(live, sid, "log_daily_record", args)["result"]
    _assert_contract_error(result)
    assert "never a dose" in result["_meta"]["clucktalk/error"]["message_en"]


def test_a_dose_in_the_treatment_note_is_rejected(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    args = {
        "house": "shed 1",
        "treatments": [{"kind": "medicine", "name": "Amoxicillin", "note": "give 2ml twice daily"}],
    }
    result = _call(live, sid, "log_daily_record", args)["result"]
    _assert_contract_error(result)
    assert "never a dose" in result["_meta"]["clucktalk/error"]["message_en"]


def test_a_treatment_note_is_acknowledged_in_the_read_back_without_speaking_its_text(fresh):
    """docs/DESIGN.md §5.1 rule 1: the read-back must be "in full" -- a note is part of what's saved, so its
    presence is spoken, even though the note's own (unpredictable) text is not (cross-modal safety, §6)."""
    live = fresh.live
    sid, _ = _session(fresh)
    args = {
        "house": "shed 1",
        "treatments": [{"kind": "medicine", "name": "Amoxicillin", "note": "given in the morning"}],
    }
    out = _ok(live, sid, "log_daily_record", args)
    assert "with a note" in out["text_en"] and "given in the morning" not in out["text_en"]
    assert out["proposed"]["treatments"][0]["note"] == "given in the morning"


@pytest.mark.parametrize(
    "args",
    [
        {"house": "shed 2", "answer": "yes"},  # a yes with nothing to answer
        {"house": "shed 2", "proposal_id": "prop_0123456789abcdef"},  # an ID without the farmer's answer
        {"house": "shed 2", "deaths": -1},  # negative deaths
        {"house": "shed 2", "treatments": [{"kind": "dose", "name": "X"}]},  # not a real treatment kind
        {"deaths": 1},  # no house at all
    ],
)
def test_malformed_requests_are_contract_errors_and_change_nothing(fresh, args):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "log_daily_record", args)["result"]
    _assert_contract_error(result)


def test_an_unknown_house_is_a_domain_error_naming_the_real_sheds(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "log_daily_record", {"house": "shed 9", "deaths": 1})["result"]
    _assert_contract_error(result)
    assert "House 1" in result["_meta"]["clucktalk/error"]["next_step_en"]


def test_a_late_yes_changes_nothing_and_asks_again(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    args = {"house": "shed 2", "deaths": 3}
    pid = _ok(live, sid, "log_daily_record", args)["proposal_id"]
    fresh.clock.t += PROPOSAL_TTL
    late = _ok(live, sid, "log_daily_record", {**args, "proposal_id": pid, "answer": "yes"})
    assert (late["status"], late["reason"], late["record"]) == ("needs_confirmation", "expired", None)


def test_latency_p95_under_500ms(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    import statistics

    samples = []
    for _ in range(40):
        t0 = time.perf_counter()
        _ok(live, sid, "log_daily_record", {"house": "shed 2", "deaths": 1})  # each propose supersedes the last
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"\nlog_daily_record HTTP round trip: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=40)")
    assert p95 < 500


def test_a_deaths_count_above_live_birds_is_rejected(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    result = _call(live, sid, "log_daily_record", {"house": "shed 1", "deaths": 999999})["result"]
    _assert_contract_error(result)
    assert "can't be right" in result["_meta"]["clucktalk/error"]["message_en"]


def test_a_backdated_correction_is_bounded_by_every_other_day_too_not_just_the_earlier_ones(fresh):
    """Rule 11 review 2026-09-29 (Critical): bounding a deaths count only against birds alive *before* that
    day let a backdated correction push the house's total deaths over birds_placed -- which used to succeed
    here ("Done. Saved") and only crash later, on the next unrelated tool call, when the overlay rebuilt the
    House and hit its own "more deaths recorded than birds placed" invariant."""
    live = fresh.live
    sid, _ = _session(fresh)
    today = {"house": "shed 1", "deaths": 3000}  # House 1: 5,000 birds placed, calm (no scripted events)
    pid = _ok(live, sid, "log_daily_record", today)["proposal_id"]
    _ok(live, sid, "log_daily_record", {**today, "proposal_id": pid, "answer": "yes"})

    backdated = {"house": "shed 1", "day": "2026-09-24", "deaths": 2500}  # 5 days before today
    result = _call(live, sid, "log_daily_record", backdated)["result"]
    _assert_contract_error(result)
    assert "can't be right" in result["_meta"]["clucktalk/error"]["message_en"]

    # The rejection changed nothing: get_farm_status still works (no invariant broken, no crash).
    status = _call(live, sid, "get_farm_status", {"house": "shed 1"})["result"]
    assert status.get("isError") in (None, False), status


# -- get_record_book, and the seed-overlay that makes get_farm_status use what was logged -----------------------


def test_record_book_declares_read_only_and_todays_scope(live):
    sid, _ = live.initialize()
    tool = _tools(live, sid)["get_record_book"]
    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["inputSchema"].get("properties", {}) == {}
    assert "today" in tool["description"]


def test_record_book_shows_nothing_logged_before_the_farmer_says_anything(fresh):
    live = fresh.live
    sid, schemas = _session(fresh)
    out = _ok(live, sid, "get_record_book", None, schemas)
    assert out["houses_total"] == 3 and out["houses_logged"] == 0
    assert all(e["logged"] is False and e["record"] is None for e in out["entries"])
    assert "No entry yet for House 1 today." in out["text_en"]


def test_record_book_reflects_a_logged_record_immediately_and_leaves_others_alone(fresh):
    live = fresh.live
    sid, schemas = _session(fresh)
    args = {"house": "shed 2", "deaths": 4, "feed_bags": 3}
    pid = _ok(live, sid, "log_daily_record", args)["proposal_id"]
    _ok(live, sid, "log_daily_record", {**args, "proposal_id": pid, "answer": "yes"})

    out = _ok(live, sid, "get_record_book", None, schemas)
    assert out["houses_logged"] == 1 and out["houses_total"] == 3
    by_number = {e["number"]: e for e in out["entries"]}
    assert by_number[2]["logged"] is True
    assert (by_number[2]["record"]["deaths"], by_number[2]["record"]["feed_bags"]) == (4, 3)
    assert by_number[1]["logged"] is False and by_number[3]["logged"] is False
    assert "House 2 logged" in out["text_en"] and "No entry yet for House 1" in out["text_en"]


def test_get_farm_status_uses_a_logged_record_the_same_day(fresh):
    """The record book is the primary data source (docs/DESIGN.md §13.2): once logged, get_farm_status must
    show it, not the seed's synthetic guess for that day."""
    live = fresh.live
    sid, _ = _session(fresh)
    args = {"house": "shed 1", "deaths": 123}
    pid = _ok(live, sid, "log_daily_record", args)["proposal_id"]
    _ok(live, sid, "log_daily_record", {**args, "proposal_id": pid, "answer": "yes"})

    result = _call(live, sid, "get_farm_status", {"house": "shed 1"})["result"]
    assert result.get("isError") in (None, False), result
    house = result["structuredContent"]["houses"][0]
    assert house["deaths_latest"] == 123


def test_three_days_later_a_logged_spike_still_shows_in_the_trailing_week():
    """The "three days later" cross-session recall scenario: a farmer's
    logged record outlives the calendar day it was logged on, because the seed's own placed_on..as_of window
    slides with "today" (docs/DESIGN.md §13.2) — so this checks the raw logged value, not an age-dependent one."""
    day_clock = DayClock(FIXED_DAY)
    now_clock = DayClock(FIXED_DAY)  # only the date matters for get_farm_status; reused as a stand-in wall clock
    source = DemoFarmSource(clock=day_clock, now=lambda: datetime.combine(now_clock.day, dtime(10, 0), tzinfo=IST))
    live, stop = _start({}, source=source)
    try:
        sid, _ = live.initialize()
        farm, as_of = source.snapshot()
        house1 = next(h for h in farm.houses if h.number == 1)
        spike = house1.records[-1].deaths + 500  # far outside any plausible natural daily count
        args = {"house": "shed 1", "deaths": spike}
        pid = _ok(live, sid, "log_daily_record", args)["proposal_id"]
        _ok(live, sid, "log_daily_record", {**args, "proposal_id": pid, "answer": "yes"})

        def status(house_ref):
            r = _call(live, sid, "get_farm_status", {"house": house_ref})["result"]
            assert r.get("isError") in (None, False), r
            return r["structuredContent"]["houses"][0]

        assert status("shed 1")["deaths_latest"] == spike

        day_clock.day += timedelta(days=3)
        now_clock.day += timedelta(days=3)
        later = status("shed 1")
        assert later["deaths_latest"] != spike  # "today" moved on: this is no longer the latest day
        assert later["deaths_7d"] >= spike  # but the spike is still inside the trailing 7-day window

        book = _ok(live, sid, "get_record_book")
        entry = next(e for e in book["entries"] if e["number"] == 1)
        assert entry["logged"] is False  # a fresh "today" has nothing logged yet
    finally:
        stop()


def test_record_book_latency_p95_under_500ms(fresh):
    live = fresh.live
    sid, _ = _session(fresh)
    import statistics

    samples = []
    for _ in range(40):
        t0 = time.perf_counter()
        _ok(live, sid, "get_record_book")
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"\nget_record_book HTTP round trip: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=40)")
    assert p95 < 500
