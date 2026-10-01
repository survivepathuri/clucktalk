"""The follow-up where the farmer meets it (docs/DESIGN.md §18), over real HTTP: answers after a vet handoff, the daily
briefing, the farm status, and the sentence at the end of a new health check. No card is involved in this file.

The wall clock of a rig is fixed, so a test that needs "later" moves it (``_advance``): an answer saved after a handoff
must be later than the handoff itself."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.follow_up import (
    FOLLOW_UP_AFTER_URGENT_DAYS,
    FOLLOW_UP_AFTER_WATCH_DAYS,
    FollowUp,
    FollowUpAnswer,
    FollowUpState,
    Outcome,
    follow_up_state,
    new_answer_id,
)
from clucktalk.domain.triage import Urgency
from tests.contract.test_follow_up_tools import (
    DONE,
    LAB,
    OFFER,
    REARING,
    REASSURANCE,
    TO_BE_SAFE,
    _ask_and_answer,
    _log_spike,
    _report,
    _rows,
    _store_check,
    _stored_check,
    world,  # noqa: F401  (a fixture)
)
from tests.contract.test_health_tools import Rig, _rig
from tests.crossmodal import spoken_numbers, unbacked_numbers


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _advance(rig: Rig, minutes: int) -> None:
    rig.source.now.t += timedelta(minutes=minutes)


def _handoff(rig: Rig, house: str = "shed 1") -> None:
    ask = rig.call("prepare_vet_handoff", house=house)["structuredContent"]
    done = rig.call("prepare_vet_handoff", house=house, proposal_id=ask["proposal_id"], answer="yes")
    assert done["structuredContent"]["status"] == "changed"


def _derive(rig: Rig, check_id: str, house_id: str = "house-1") -> FollowUp:
    """The follow-up's state straight from the store with the domain function, with the handoff times."""
    src = rig.source
    farm, today = src.snapshot()
    house = next(h for h in farm.houses if h.house_id == house_id)
    check = src.store.get_health_check(check_id)
    assert check is not None
    checks = src.store.recent_health_checks(farm.farm_id, house_id, date.min)
    handed = {c.check_id: h.created_at for c in checks if (h := src.store.handoff_for_check(c.check_id)) is not None}
    return follow_up_state(check, src.store.follow_up_answers(farm.farm_id, check_id), handed, house, today, checks)


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def due_line(label: str, n: int) -> str:
    return (
        f"{label}: your health check {_days(n)} ago needs a follow-up. "
        "How are the birds now: better, the same, or worse?"
    )


def escalated_line(label: str, n: int) -> str:
    return f"{label}: the follow-up on the health check {_days(n)} ago still needs attention. {TO_BE_SAFE}"


def lapsed_line(label: str, n: int) -> str:
    return f"{label}: there was no answer to the follow-up on the health check {_days(n)} ago."


def _scan_item(text: str) -> None:
    for rule in (REASSURANCE, LAB, REARING):
        assert not rule.search(text), (rule.pattern, text)
    for word in ("supersede", "remind", "notify", "follow_up"):
        assert word not in text.lower(), (word, text)


def _brief(rig: Rig, **args) -> dict:
    result = rig.call("get_daily_briefing", **args)
    assert result.get("isError") in (None, False), result
    sc = result["structuredContent"]
    assert unbacked_numbers(sc, sc["text_en"], sc["text_te"]) == [], sc["text_en"]
    assert sorted(spoken_numbers(sc["text_en"], set())) == sorted(spoken_numbers(sc["text_te"], set()))
    assert len(sc["items"]) <= 5
    return sc


def _item(sc: dict, fact_id: str) -> dict | None:
    return next((i for i in sc["items"] if i["fact_id"] == fact_id), None)


def _status(rig: Rig, **args) -> dict:
    result = rig.call("get_farm_status", **args)
    assert result.get("isError") in (None, False), result
    sc = result["structuredContent"]
    assert unbacked_numbers(sc, sc["text_en"], sc["text_te"]) == [], sc["text_en"]
    assert sorted(spoken_numbers(sc["text_en"], set())) == sorted(spoken_numbers(sc["text_te"], set()))
    return sc


# -- after a vet handoff, a worse bird is still heard ----------------------------------------------
@pytest.mark.parametrize("outcome", ["same", "worse", "not_sure"])
def test_not_better_after_a_handoff_is_accepted_saved_and_escalates(rig, outcome):
    cid = _stored_check(rig)
    _ask_and_answer(rig, "worse")  # before the handoff
    _handoff(rig)
    handoff_id = rig.source.store.handoff_for_check(cid).handoff_id
    _advance(rig, 30)
    first, second = _ask_and_answer(rig, outcome)
    ask, sc = first["structuredContent"], second["structuredContent"]
    assert ask["status"] == "needs_confirmation" and ask["escalated"] is True and TO_BE_SAFE in ask["text_en"]
    assert ask["handoff_offered"] is False and OFFER not in ask["text_en"]  # one handoff per check: no second offer
    assert sc["status"] == "changed" and sc["state"] == "escalated" and sc["escalated"] is True
    assert sc["text_en"] == f"{DONE} {TO_BE_SAFE}" and sc["handoff_offered"] is False
    assert sc["reasons"] == [f"said_{outcome}"] and sc["urgency"] == "watch"
    assert len(_rows(rig, cid)) == 2
    assert rig.source.store.handoff_for_check(cid).handoff_id == handoff_id  # nothing was sent by this tool
    for text in (ask["text_en"], sc["text_en"]):
        assert "no health check waiting" not in text.lower()


def test_better_after_a_handoff_is_accepted_and_only_closes(rig):
    cid = _stored_check(rig)
    _ask_and_answer(rig, "worse")
    _handoff(rig)
    _advance(rig, 30)
    first, second = _ask_and_answer(rig, "better")
    sc = second["structuredContent"]
    assert first["structuredContent"]["status"] == "needs_confirmation"
    assert (sc["status"], sc["state"], sc["escalated"], sc["text_en"]) == ("changed", "closed", False, DONE)
    assert sc["urgency"] == "watch" and len(_rows(rig, cid)) == 2  # urgency never lowered; the answer is on file
    assert rig.call("get_health_check", house="shed 1")["structuredContent"]["urgency"] == "watch"


def test_the_most_severe_answer_after_the_handoff_still_wins(rig):
    cid = _stored_check(rig)
    _handoff(rig)
    _advance(rig, 30)
    _ask_and_answer(rig, "worse")
    _advance(rig, 30)
    _, later = _ask_and_answer(rig, "better")
    sc = later["structuredContent"]
    assert sc["state"] == "escalated" and sc["recorded_as"] == "worse" and len(_rows(rig, cid)) == 2


@pytest.mark.parametrize("outcome", ["better", "same", "worse", "not_sure"])
def test_a_handed_off_check_is_never_told_there_is_nothing_waiting(rig, outcome):
    _stored_check(rig)
    _ask_and_answer(rig, "worse")
    _handoff(rig)
    _advance(rig, 30)
    result = _report(rig, outcome)
    assert result.get("isError") in (None, False), result
    assert result["structuredContent"]["status"] == "needs_confirmation"


def test_a_repeated_yes_for_an_answer_given_before_the_handoff_is_still_a_replay(rig):
    cid = _stored_check(rig)
    first, _ = _ask_and_answer(rig, "worse")
    _handoff(rig)
    _advance(rig, 30)
    replay = _report(rig, "worse", proposal_id=first["structuredContent"]["proposal_id"], answer="yes")
    assert replay["structuredContent"]["replayed"] is True and len(_rows(rig, cid)) == 1


# -- the briefing ----------------------------------------------------------------------------------
def test_a_due_unanswered_follow_up_is_a_pinned_question_for_that_shed(rig):
    _stored_check(rig)  # a watch check three days ago: due today
    sc = _brief(rig)
    item = _item(sc, "follow_up:house-1")
    assert item is not None and item["pinned"] is True and item["level"] == "watch"
    assert item["text_en"] == due_line("House 1", 3)
    assert item["values"]["days_ago"] == 3 and item["values"]["state"] == "due"
    assert _item(sc, "open_health_check:house-1") is None  # never both for one shed
    assert item["text_te"].strip() and item["text_te"] != item["text_en"]
    _scan_item(item["text_en"])


@pytest.mark.parametrize(("days_ago", "urgency"), [(1, Urgency.URGENT), (3, Urgency.WATCH), (4, Urgency.WATCH)])
def test_the_days_since_the_check_are_the_real_number_of_days(rig, days_ago, urgency):
    _store_check(rig.source, days_ago=days_ago, urgency=urgency)
    item = _item(_brief(rig), "follow_up:house-1")
    assert item is not None and item["values"]["days_ago"] == days_ago
    if urgency is Urgency.WATCH:
        assert item["text_en"] == due_line("House 1", days_ago)  # "1 day ago", "3 days ago": from the clock, not typed
    else:  # an urgent check keeps its own warning first (review finding B1); the question follows it
        assert item["text_en"].endswith(due_line("House 1", days_ago))
        assert "needs a vet today" in item["text_en"]


def test_an_escalated_follow_up_ranks_first_with_the_safe_line(rig):
    _stored_check(rig)
    _ask_and_answer(rig, "worse")
    sc = _brief(rig)
    first = sc["items"][0]
    assert first["fact_id"] == "follow_up:house-1" and first["level"] == "alert" and first["pinned"] is True
    assert first["text_en"] == escalated_line("House 1", 3) and first["values"]["state"] == "escalated"
    assert TO_BE_SAFE in sc["text_en"] and "vet or doctor" in sc["text_en"]
    _scan_item(first["text_en"])


def test_an_escalated_follow_up_stays_when_only_a_newer_lower_check_exists(rig):
    cid = _stored_check(rig, days_ago=3, urgency=Urgency.URGENT)
    _ask_and_answer(rig, "worse")
    _stored_check(rig, days_ago=1, urgency=Urgency.WATCH)  # newer, lower: the briefing's own rule would show this one
    sc = _brief(rig)
    item = _item(sc, "follow_up:house-1")
    assert item is not None and item["values"]["days_ago"] == 3 and item["values"]["state"] == "escalated"
    assert _item(sc, "open_health_check:house-1") is None
    assert _derive(rig, cid).state is FollowUpState.ESCALATED


def test_a_newer_check_of_equal_urgency_takes_the_escalation_over(rig):
    cid = _stored_check(rig, days_ago=3, urgency=Urgency.URGENT)
    _ask_and_answer(rig, "worse")
    _stored_check(rig, days_ago=1, urgency=Urgency.URGENT)
    sc = _brief(rig)
    item = _item(sc, "follow_up:house-1")
    assert _derive(rig, cid).state is FollowUpState.SUPERSEDED
    assert (
        item is not None and item["values"]["days_ago"] == 1 and item["values"]["state"] == "due"
    )  # the newer check's


def test_a_handoff_ends_the_escalation_in_the_briefing_until_something_new_is_said(rig):
    cid = _stored_check(rig)
    _ask_and_answer(rig, "worse")
    assert _item(_brief(rig), "follow_up:house-1")["values"]["state"] == "escalated"
    _handoff(rig)
    sc = _brief(rig)
    assert _item(sc, "follow_up:house-1") is None and _item(sc, "open_health_check:house-1") is not None
    _advance(rig, 30)
    _ask_and_answer(rig, "worse")  # worse again after the handoff
    sc = _brief(rig)
    again = _item(sc, "follow_up:house-1")
    assert again is not None and again["values"]["state"] == "escalated" and again["level"] == "alert"
    assert _item(sc, "open_health_check:house-1") is None and _derive(rig, cid).handed_off is True


def test_a_closed_follow_up_is_not_in_the_briefing(rig):
    _stored_check(rig)
    _ask_and_answer(rig, "better")
    assert _item(_brief(rig), "follow_up:house-1") is None


def test_a_follow_up_not_yet_due_is_not_in_the_briefing(rig):
    _stored_check(rig, days_ago=1, urgency=Urgency.WATCH)  # due in two days (shed 1 is the shed with no seeded spike)
    assert _item(_brief(rig), "follow_up:house-1") is None


def test_every_shed_has_one_health_item_and_the_list_stays_within_five(rig):
    for house, shed in (("house-1", "shed 1"), ("house-2", "shed 2"), ("house-3", "shed 3")):
        _store_check(rig.source, days_ago=3, urgency=Urgency.URGENT, house_id=house)
        _ask_and_answer(rig, "worse", house=shed)
    sc = _brief(rig)
    ids = [i["fact_id"] for i in sc["items"]]
    assert len(ids) == len(set(ids)) and len(ids) <= 5
    for n in (1, 2, 3):
        both = [i for i in ids if i in (f"follow_up:house-{n}", f"open_health_check:house-{n}")]
        assert both == [f"follow_up:house-{n}"], ids
    assert [i["fact_id"] for i in sc["items"][:3]] == [f"follow_up:house-{n}" for n in (1, 2, 3)]


def test_the_follow_up_item_never_makes_a_promise_or_gives_advice(rig):
    _stored_check(rig)
    due = _item(_brief(rig), "follow_up:house-1")
    _ask_and_answer(rig, "worse")
    escalated = _item(_brief(rig), "follow_up:house-1")
    for item in (due, escalated):
        _scan_item(item["text_en"])
        assert not re.search(r"\b(?:i'll|i will|we will|will call|will message)\b", item["text_en"].lower())


# -- the farm status -------------------------------------------------------------------------------
def test_status_has_a_follow_up_field_and_one_spoken_line_for_a_due_follow_up(rig):
    cid = _stored_check(rig)
    sc = _status(rig, house="shed 1")
    (house,) = sc["houses"]
    fu = house["follow_up"]
    assert fu["check_id"] == cid and fu["state"] == "due" and fu["days_ago"] == 3 and fu["urgency"] == "watch"
    assert fu["text_en"] == due_line("House 1", 3) and fu["text_te"].strip() and fu["handed_off"] is False
    assert sc["text_en"].count(fu["text_en"]) == 1  # one spoken line for the shed
    _scan_item(fu["text_en"])


def test_status_for_a_shed_without_a_follow_up_has_none_and_says_nothing_about_one(rig):
    _stored_check(rig)
    sc = _status(rig)
    by_number = {h["number"]: h for h in sc["houses"]}
    assert by_number[1]["follow_up"] is not None
    assert by_number[2]["follow_up"] is None and by_number[3]["follow_up"] is None
    assert sc["text_en"].count("needs a follow-up") == 1


def test_status_whole_farm_reads_the_line_inside_the_sheds_own_item(rig):
    _stored_check(rig)
    sc = _status(rig)
    assert due_line("House 1", 3) in sc["text_en"]
    assert sc["text_en"].count("How are the birds now") == 1


def test_status_escalated_closed_lapsed_and_scheduled_use_the_domain_states(rig):
    cid = _stored_check(rig)
    _ask_and_answer(rig, "worse")
    fu = _status(rig, house="shed 1")["houses"][0]["follow_up"]
    assert fu["state"] == "escalated" and fu["text_en"] == escalated_line("House 1", 3)
    assert fu["reasons"] == ["said_worse"] and fu["outcome"] == "worse" and fu["check_id"] == cid


def test_status_scheduled_has_the_field_but_no_spoken_line(rig):
    _stored_check(rig, days_ago=2, urgency=Urgency.WATCH)  # not yet due
    sc = _status(rig, house="shed 1")
    scheduled = sc["houses"][0]["follow_up"]
    assert scheduled["state"] == "scheduled" and scheduled["text_en"] is None and scheduled["days_ago"] == 2
    assert "follow-up" not in sc["text_en"].lower()


def test_status_closed_has_no_spoken_line(rig):
    _stored_check(rig)
    _ask_and_answer(rig, "better")
    closed = _status(rig, house="shed 1")
    assert closed["houses"][0]["follow_up"]["state"] == "closed" and closed["houses"][0]["follow_up"]["text_en"] is None
    assert "follow-up" not in closed["text_en"].lower()


def test_status_lapsed_says_so_honestly_and_never_reads_as_better(rig):
    _stored_check(rig, days_ago=12, urgency=Urgency.WATCH)
    lapsed = _status(rig, house="shed 1")["houses"][0]["follow_up"]
    assert lapsed["state"] == "lapsed" and lapsed["days_ago"] == 12 and lapsed["outcome"] is None
    assert lapsed["text_en"] == lapsed_line("House 1", 12)
    assert "better" not in lapsed["text_en"]


def test_status_after_a_handoff_hides_the_escalation_and_shows_it_again_after_a_new_worse(rig):
    _stored_check(rig)
    _ask_and_answer(rig, "worse")
    _handoff(rig)
    assert _status(rig, house="shed 1")["houses"][0]["follow_up"] is None  # handled by the vet handoff
    _advance(rig, 30)
    _ask_and_answer(rig, "worse")
    again = _status(rig, house="shed 1")["houses"][0]["follow_up"]
    assert again["state"] == "escalated" and again["handed_off"] is True


def test_status_states_are_the_domains_and_never_none_or_superseded(rig):
    _stored_check(rig)
    sc = _status(rig)
    allowed = {s.value for s in FollowUpState} - {"none", "superseded"}
    for house in sc["houses"]:
        if house["follow_up"] is not None:
            assert house["follow_up"]["state"] in allowed


# -- the sentence at the end of a new health check -------------------------------------------------
def _sentence(label: str, n: int) -> str:
    return f"The next briefing, in about {_days(n)}, will ask how {label} is doing."


def test_a_new_watch_check_says_when_the_next_briefing_will_ask(rig):
    sc = rig.call("start_health_check", house="shed 1", signs=["coughing"])["structuredContent"]
    assert sc["floor_urgency"] == "watch"
    assert _sentence("House 1", FOLLOW_UP_AFTER_WATCH_DAYS) in sc["text_en"]
    assert sc["follow_up_in_days"] == FOLLOW_UP_AFTER_WATCH_DAYS
    assert unbacked_numbers(sc, sc["text_en"], sc["text_te"]) == []


def test_a_new_urgent_check_uses_the_urgent_window(rig):
    sc = rig.call("start_health_check", house="shed 1", signs=["swollen_head"])["structuredContent"]
    assert sc["floor_urgency"] == "urgent"
    assert _sentence("House 1", FOLLOW_UP_AFTER_URGENT_DAYS) in sc["text_en"]
    assert sc["follow_up_in_days"] == FOLLOW_UP_AFTER_URGENT_DAYS


def test_a_check_answered_at_once_for_a_suspected_reportable_disease_says_it_too(rig):
    sc = rig.call("start_health_check", house="shed 2", signs=["swollen_head", "discoloured_comb"])["structuredContent"]
    assert sc["status"] == "ready" and sc["urgency"] == "notifiable_suspect"
    assert _sentence("House 2", FOLLOW_UP_AFTER_URGENT_DAYS) in sc["text_en"]


def test_the_sentence_promises_nothing_proactive_and_is_only_on_the_start(rig):
    sc = rig.call("start_health_check", house="shed 1", signs=["coughing"])["structuredContent"]
    sentence = _sentence("House 1", FOLLOW_UP_AFTER_WATCH_DAYS)
    assert not re.search(r"remind|notify|alert you|call you|message|text you|i'll|superseded", sentence.lower())
    assert sc["text_te"].strip() and sc["text_te"] != sc["text_en"]
    rig.runner.run_all()
    later = rig.call("get_health_check", check_id=sc["check_id"])["structuredContent"]
    assert "The next briefing" not in later["text_en"] and later["follow_up_in_days"] is None
    again = rig.call("start_health_check", house="shed 1", signs=["coughing"])["structuredContent"]
    assert again["duplicate"] is True and sentence in again["text_en"]  # a repeated start is still a start


# -- the whole chain across restarts, on a real file -----------------------------------------------
def test_three_days_later_after_a_restart_the_briefing_asks_and_worse_escalates_and_survives(world):  # noqa: F811
    rig = world.boot(0)
    check = rig.call("start_health_check", house="shed 1", signs=["coughing"])["structuredContent"]
    rig.runner.run_all()
    cid = check["check_id"]
    assert _sentence("House 1", FOLLOW_UP_AFTER_WATCH_DAYS) in check["text_en"]
    world.down()

    rig = world.boot(FOLLOW_UP_AFTER_WATCH_DAYS)  # a new server on the same file, three days on
    asked = _item(_brief(rig), "follow_up:house-1")
    assert asked is not None and asked["text_en"] == due_line("House 1", FOLLOW_UP_AFTER_WATCH_DAYS)
    _ask_and_answer(rig, "worse")
    before = _derive(rig, cid)
    world.down()

    rig = world.boot(FOLLOW_UP_AFTER_WATCH_DAYS, minutes=20)
    assert _derive(rig, cid) == before and before.state is FollowUpState.ESCALATED
    esc = _item(_brief(rig), "follow_up:house-1")
    assert esc is not None and esc["text_en"] == escalated_line("House 1", FOLLOW_UP_AFTER_WATCH_DAYS)
    _handoff(rig)
    assert _item(_brief(rig), "follow_up:house-1") is None  # the vet has the summary
    world.down()

    rig = world.boot(FOLLOW_UP_AFTER_WATCH_DAYS + 1)  # the next day: worse again, after the handoff
    assert _item(_brief(rig), "follow_up:house-1") is None
    _, saved = _ask_and_answer(rig, "worse")
    assert saved["structuredContent"]["state"] == "escalated" and saved["structuredContent"]["handoff_offered"] is False
    again = _item(_brief(rig), "follow_up:house-1")
    assert again is not None and again["values"]["state"] == "escalated"
    world.down()


def test_a_death_spike_after_the_handoff_escalates_again_through_a_restart(world):  # noqa: F811
    rig = world.boot(0)
    cid = rig.call("start_health_check", house="shed 1", signs=["coughing"])["structuredContent"]["check_id"]
    rig.runner.run_all()
    world.down()
    rig = world.boot(3)
    _ask_and_answer(rig, "same")
    _handoff(rig)
    assert _derive(rig, cid).state is FollowUpState.SUPERSEDED
    world.down()
    rig = world.boot(4)  # a later day than the handoff
    deaths = _log_spike(rig)
    first, second = _ask_and_answer(rig, "better")
    assert str(deaths) in first["structuredContent"]["text_en"].replace(",", "")  # recorded as not better
    assert second["structuredContent"]["state"] == "escalated" and _rows(rig, cid)[-1].records_worse is True
    assert second["structuredContent"]["handoff_offered"] is False
    world.down()


def test_a_shed_with_two_escalated_follow_ups_shows_the_more_urgent_one(rig):
    """The urgent check (4 days ago) and a newer, lower watch check (3 days ago) were both answered "worse". The
    lower one does not replace the urgent one (decision: only an equal or higher check does), and the shed's one
    follow-up item is the urgent one, in the briefing and in the status."""
    urgent = _store_check(rig.source, days_ago=4, urgency=Urgency.URGENT)
    watch = _store_check(rig.source, days_ago=3, urgency=Urgency.WATCH)
    for cid in (urgent, watch):
        saved = FollowUpAnswer(
            new_answer_id(),
            rig.source.farm_id,
            "house-1",
            cid,
            Outcome.WORSE,
            False,
            "prop_" + "a" * 16,
            rig.source.now(),
        )
        rig.source.store.add_follow_up_answer(saved)
    item = _item(_brief(rig), "follow_up:house-1")
    assert (
        item["values"]["urgency"] == "urgent"
        and item["values"]["days_ago"] == 4
        and item["values"]["state"] == "escalated"
    )
    shown = _status(rig, house="shed 1")["houses"][0]["follow_up"]
    assert shown["check_id"] == urgent and shown["urgency"] == "urgent"


def test_the_briefing_and_status_stay_fast_with_many_stored_checks(rig):
    import statistics
    import time

    for days_ago in range(1, 61):  # two months of checks on one shed
        _store_check(rig.source, days_ago=days_ago, urgency=Urgency.WATCH)
    for call in (lambda: _brief(rig), lambda: _status(rig)):
        samples = []
        for _ in range(20):
            t0 = time.perf_counter()
            call()
            samples.append((time.perf_counter() - t0) * 1000)
        p95 = statistics.quantiles(samples, n=20)[18]
        print(f"with 60 stored checks: p50 {statistics.median(samples):.1f} ms, p95 {p95:.1f} ms (n=20)")
        assert p95 < 500
