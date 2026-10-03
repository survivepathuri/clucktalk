"""Flock follow-up, domain layer (docs/DESIGN.md §18).

``follow_up_state`` is a pure function of (health check, stored answers, confirmed handoffs, the house's record book,
the injected ``today``). No I/O, no model, no clock of its own. Expected values are written by hand from the design's
state table, never copied from code output."""

from __future__ import annotations

import ast
import itertools
import re
import time
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path

import pytest

from clucktalk.domain import follow_up as fu
from clucktalk.domain.briefing import _check_to_show, check_urgency
from clucktalk.domain.follow_up import (
    EscalationReason,
    FollowUpAnswer,
    FollowUpState,
    Outcome,
    follow_up_state,
    new_answer_id,
)
from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.triage import (
    CheckStatus,
    Floor,
    HealthCheck,
    Sign,
    TriageInput,
    TriageResult,
    Urgency,
    new_check_id,
)

IST = timezone(timedelta(hours=5, minutes=30))
CHECK_DAY = date(2026, 10, 10)
PLACED = date(2026, 9, 1)
SRC = Path(__file__).resolve().parents[2] / "src" / "clucktalk"

S = FollowUpState
O = Outcome  # noqa: E741  (a short alias keeps the tables below readable)
ESCALATING = (O.SAME, O.WORSE, O.NOT_SURE)


# -- builders -------------------------------------------------------------------------------------------------
def _input(house_id: str = "house-1") -> TriageInput:
    return TriageInput(house_id, "House 1", "షెడ్ 1", "Ross 308", 40, 900, (Sign.COUGHING,), None, None, None,
                       2, 1.0, False, None, CHECK_DAY.isoformat())  # fmt: skip


def _check(
    urgency: Urgency = Urgency.WATCH,
    *,
    day: date = CHECK_DAY,
    status: CheckStatus = CheckStatus.READY,
    house_id: str = "house-1",
    hour: int = 10,
) -> HealthCheck:
    at = datetime.combine(day, dtime(hour, 0), tzinfo=IST)
    result = None
    if status is CheckStatus.READY:
        result = TriageResult(urgency, (), (), "rules", None, None)
    return HealthCheck(new_check_id(), "farm", house_id, at, status, _input(house_id), Floor(urgency, ()), result, at)


def _house(spike_day: date | None = None, *, house_id: str = "house-1", last: date = date(2026, 11, 30)) -> House:
    """One broiler-ish house with a flat 2 deaths a day from PLACED to ``last``; ``spike_day`` has 400 deaths."""
    records = []
    day = PLACED
    while day <= last:
        records.append(DailyRecord(day, 400 if day == spike_day else 2, 100.0))
        day += timedelta(days=1)
    return House(house_id, 1, HouseKind.BROILER, "Ross 308", PLACED, 5000, 0, 500.0, tuple(records))


def _answer(check: HealthCheck, said: Outcome, *, hours: int = 0) -> FollowUpAnswer:
    at = check.created_at + timedelta(days=3, hours=hours)
    return FollowUpAnswer(
        new_answer_id(), check.farm_id, check.house_id, check.check_id, said, False, "prop_" + "a" * 16, at
    )


def _state(check, answers=(), *, today, handed=(), spike_day=None, others=()):
    return follow_up_state(check, tuple(answers), frozenset(handed), _house(spike_day), today, others)


# -- the time windows: named constants, one place, our own rules ----------------------------------------------
def test_the_time_windows_are_named_and_have_the_designed_values():
    assert fu.FOLLOW_UP_AFTER_WATCH_DAYS == 3
    assert fu.FOLLOW_UP_AFTER_URGENT_DAYS == 1  # urgent AND suspected reportable disease
    assert fu.FOLLOW_UP_LAPSE_AFTER_DUE_DAYS == 7


def test_the_time_windows_say_they_are_our_own_rules_not_sourced_figures():
    text = (SRC / "domain" / "follow_up.py").read_text(encoding="utf-8")
    block = text[: text.index("FOLLOW_UP_AFTER_WATCH_DAYS")]
    assert "our own" in block.lower() and "not sourced" in block.lower()


WINDOW_NAMES = ("FOLLOW_UP_AFTER_WATCH_DAYS", "FOLLOW_UP_AFTER_URGENT_DAYS", "FOLLOW_UP_LAPSE_AFTER_DUE_DAYS")


def _python_files():
    return [p for p in SRC.rglob("*.py")]


def test_the_time_windows_are_defined_only_in_the_follow_up_module():
    defined_in: dict[str, list[str]] = {n: [] for n in WINDOW_NAMES}
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = [t for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target]
            for t in targets:
                if t.id in defined_in:
                    defined_in[t.id].append(path.relative_to(SRC).as_posix())
    assert defined_in == {n: ["domain/follow_up.py"] for n in WINDOW_NAMES}, defined_in


def test_no_bare_day_count_hides_inside_the_follow_up_module():
    """Every timedelta in the module is built from a name, never from a literal number of days."""
    tree = ast.parse((SRC / "domain" / "follow_up.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "timedelta":
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                assert not isinstance(arg, ast.Constant), f"literal day count at line {node.lineno}"


# -- purity: no I/O, no model, no clock of its own ------------------------------------------------------------
def test_the_domain_module_has_no_io_model_or_clock_imports():
    tree = ast.parse((SRC / "domain" / "follow_up.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    banned = ("sqlite3", "boto3", "botocore", "socket", "os", "subprocess", "httpx", "requests", "logging",
              "clucktalk.store", "clucktalk.agents", "clucktalk.server", "time")  # fmt: skip
    assert not [m for m in imported if m in banned or m.startswith(tuple(b + "." for b in banned))], imported


def test_the_domain_module_never_reads_the_real_time():
    tree = ast.parse((SRC / "domain" / "follow_up.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"today", "now", "utcnow", "monotonic", "perf_counter", "time"}, node.lineno


def test_the_clock_is_a_parameter_so_any_date_works():
    check = _check(Urgency.WATCH)
    for today in (date(2020, 1, 1), date(2026, 10, 10), date(2040, 6, 1)):
        assert follow_up_state(check, (), frozenset(), _house(), today).state in set(S)
    far_past = follow_up_state(check, (), frozenset(), _house(), date(2020, 1, 1))
    assert far_past.state is S.SCHEDULED and far_past.due_day == CHECK_DAY + timedelta(days=3)


def test_the_same_inputs_give_the_same_answer_and_nothing_is_changed():
    check = _check(Urgency.URGENT)
    answers = (_answer(check, O.BETTER),)
    snapshot = tuple(answers)
    first = _state(check, answers, today=CHECK_DAY + timedelta(days=4))
    assert first == _state(check, answers, today=CHECK_DAY + timedelta(days=4))
    assert answers == snapshot


def test_one_call_takes_well_under_a_millisecond():
    check = _check(Urgency.URGENT)
    answers = tuple(_answer(check, o) for o in (O.BETTER, O.SAME, O.NOT_SURE, O.WORSE))
    house = _house(CHECK_DAY + timedelta(days=2))  # 90 records, a spike to find
    today = CHECK_DAY + timedelta(days=5)
    follow_up_state(check, answers, frozenset(), house, today)  # warm-up
    runs = 500
    t0 = time.perf_counter()
    for _ in range(runs):
        follow_up_state(check, answers, frozenset(), house, today)
    per_call_ms = (time.perf_counter() - t0) * 1000 / runs
    assert per_call_ms < 1.0, per_call_ms


# -- none -----------------------------------------------------------------------------------------------------
def test_a_routine_check_has_no_follow_up():
    fup = _state(_check(Urgency.ROUTINE), today=CHECK_DAY + timedelta(days=30))
    assert fup.state is S.NONE and fup.due_day is None and fup.outcome is None and fup.reasons == ()


def test_a_check_still_analyzing_has_no_follow_up_yet():
    fup = _state(_check(Urgency.URGENT, status=CheckStatus.ANALYZING), today=CHECK_DAY + timedelta(days=2))
    assert fup.state is S.NONE


@pytest.mark.parametrize("urgency", [Urgency.WATCH, Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT])
def test_a_failed_check_is_followed_up_at_the_level_the_farmer_was_told(urgency):
    check = _check(urgency, status=CheckStatus.FAILED)
    fup = _state(check, today=CHECK_DAY + timedelta(days=5))
    assert fup.state is S.DUE and fup.urgency is urgency  # the code floor, as in get_health_check


@pytest.mark.parametrize("status", [CheckStatus.READY, CheckStatus.FAILED, CheckStatus.ANALYZING])
@pytest.mark.parametrize("urgency", list(Urgency))
def test_the_urgency_shown_equals_what_the_briefing_tells_the_farmer(urgency, status):
    check = _check(urgency, status=status)
    fup = _state(check, today=CHECK_DAY + timedelta(days=5))
    assert fup.urgency is check_urgency(check)


# -- scheduled, due, lapsed: the clock only -------------------------------------------------------------------
@pytest.mark.parametrize(
    ("urgency", "days_to_due"),
    [(Urgency.WATCH, 3), (Urgency.URGENT, 1), (Urgency.NOTIFIABLE_SUSPECT, 1)],
)
def test_a_follow_up_is_due_three_days_after_watch_and_one_day_after_urgent_or_reportable(urgency, days_to_due):
    check = _check(urgency)
    due_day = CHECK_DAY + timedelta(days=days_to_due)
    before = _state(check, today=due_day - timedelta(days=1))
    on = _state(check, today=due_day)
    assert (before.state, before.due_day) == (S.SCHEDULED, due_day)
    assert (on.state, on.due_day) == (S.DUE, due_day)
    assert before.outcome is None and on.outcome is None and before.reasons == on.reasons == ()


def test_the_day_of_the_check_is_scheduled_not_due_even_for_urgent():
    assert _state(_check(Urgency.URGENT), today=CHECK_DAY).state is S.SCHEDULED


@pytest.mark.parametrize("urgency", [Urgency.WATCH, Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT])
def test_lapsed_only_after_seven_days_past_due(urgency):
    check = _check(urgency)
    due_day = _state(check, today=CHECK_DAY).due_day
    assert _state(check, today=due_day + timedelta(days=6)).state is S.DUE
    assert _state(check, today=due_day + timedelta(days=7)).state is S.DUE  # the seventh day is still due
    # M5 (Step 47C): only a watch check lapses; an unanswered urgent or reportable one escalates instead
    expected = S.LAPSED if urgency is Urgency.WATCH else S.ESCALATED
    assert _state(check, today=due_day + timedelta(days=8)).state is expected


@pytest.mark.parametrize("urgency", [Urgency.WATCH, Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT])
def test_no_answer_never_counts_as_better_not_even_lapsed(urgency):
    check = _check(urgency)
    for offset in range(0, 60):
        fup = _state(check, today=CHECK_DAY + timedelta(days=offset))
        # M5 (Step 47C): the urgent / reportable ones end ESCALATED (never closed, never "better"), a watch one LAPSED
        assert fup.state in {S.SCHEDULED, S.DUE, S.LAPSED, S.ESCALATED}
        assert fup.outcome is None and fup.state is not S.CLOSED
        assert fup.reasons == () or fup.state is S.ESCALATED
    late = _state(check, today=CHECK_DAY + timedelta(days=40)).state
    assert late is (S.LAPSED if urgency is Urgency.WATCH else S.ESCALATED)


# -- better closes, and only closes ---------------------------------------------------------------------------
@pytest.mark.parametrize("urgency", [Urgency.WATCH, Urgency.URGENT])
def test_better_closes_the_follow_up_and_nothing_else(urgency):
    check = _check(urgency)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4))
    assert (fup.state, fup.outcome, fup.reasons, fup.urgency) == (S.CLOSED, O.BETTER, (), urgency)


@pytest.mark.parametrize("offset", [0, 1, 3, 10, 40])
def test_better_closes_before_due_and_after_lapse_too(offset):
    check = _check(Urgency.WATCH)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=offset))
    assert fup.state is S.CLOSED


@pytest.mark.parametrize("urgency", list(Urgency))
@pytest.mark.parametrize("said", [None, *O])
@pytest.mark.parametrize("spike", [False, True])
@pytest.mark.parametrize("handed", [False, True])
def test_no_answer_ever_lowers_or_clears_the_checks_urgency(urgency, said, spike, handed):
    check = _check(urgency)
    answers = () if said is None else (_answer(check, said),)
    today = CHECK_DAY + timedelta(days=4)
    fup = _state(
        check, answers, today=today, handed=[check.check_id] if handed else [],
        spike_day=CHECK_DAY + timedelta(days=2) if spike else None,
    )  # fmt: skip
    assert fup.urgency is urgency
    assert fup.check_id == check.check_id


# -- same, worse, not sure escalate ---------------------------------------------------------------------------
@pytest.mark.parametrize("urgency", [Urgency.WATCH, Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT])
@pytest.mark.parametrize(
    ("said", "reason"),
    [
        (O.SAME, EscalationReason.SAID_SAME),
        (O.WORSE, EscalationReason.SAID_WORSE),
        (O.NOT_SURE, EscalationReason.SAID_NOT_SURE),
    ],
)
@pytest.mark.parametrize("offset", [0, 2, 5, 30])  # before due, due, lapsed: an answer is an answer
def test_same_worse_and_not_sure_always_escalate(urgency, said, reason, offset):
    check = _check(urgency)
    fup = _state(check, [_answer(check, said)], today=CHECK_DAY + timedelta(days=offset))
    assert fup.state is S.ESCALATED and fup.outcome is said and reason in fup.reasons


def test_the_escalation_reasons_are_codes_not_sentences():
    assert {r.value for r in EscalationReason} == {
        "said_same", "said_worse", "said_not_sure", "record_book_spike", "reportable_without_vet_handoff",
    }  # fmt: skip
    assert all(re.fullmatch(r"[a-z_]+", r.value) for r in EscalationReason)


# -- a death spike after the check ----------------------------------------------------------------------------
@pytest.mark.parametrize("urgency", [Urgency.WATCH, Urgency.URGENT])
def test_a_spike_in_the_record_book_after_the_check_makes_better_count_as_worse(urgency):
    check = _check(urgency)
    spike_day = CHECK_DAY + timedelta(days=2)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4), spike_day=spike_day)
    assert fup.state is S.ESCALATED and fup.outcome is O.WORSE
    assert EscalationReason.RECORD_BOOK_SPIKE in fup.reasons and fup.spike_day == spike_day
    assert fup.urgency is urgency


@pytest.mark.parametrize("said", [O.SAME, O.NOT_SURE, O.WORSE])
def test_a_spike_makes_any_answer_count_as_worse(said):
    check = _check(Urgency.WATCH)
    fup = _state(
        check, [_answer(check, said)], today=CHECK_DAY + timedelta(days=4), spike_day=CHECK_DAY + timedelta(days=1)
    )
    assert fup.outcome is O.WORSE and EscalationReason.RECORD_BOOK_SPIKE in fup.reasons


def test_a_spike_with_no_answer_yet_is_already_an_escalation():
    check = _check(Urgency.WATCH)
    fup = _state(check, today=CHECK_DAY + timedelta(days=1), spike_day=CHECK_DAY + timedelta(days=1))
    assert fup.state is S.ESCALATED and fup.outcome is O.WORSE and fup.reasons == (EscalationReason.RECORD_BOOK_SPIKE,)


def _check_that_saw(check: HealthCheck, *, latest_day: date | None, deaths: int | None, spike: bool) -> HealthCheck:
    """``check`` as if its stored input had captured the record book's latest count (day, deaths, spike flag)."""
    seen = replace(
        check.input,
        latest_record_day=latest_day.isoformat() if latest_day else None,
        deaths_latest=deaths,
        mortality_spike=spike,
    )
    return replace(check, input=seen)


# Step 47B part C (review finding H2, approved option 1): the old test was one test with two cases. Its old
# meaning is kept here for the cases where the check had already SEEN the spike (or the spike is older than the
# check); the new case, where the check-day record shows more deaths than the check stored, is the next test.
def test_a_spike_before_the_check_or_one_the_check_already_saw_is_not_news():
    check = _check(Urgency.WATCH)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4),
                 spike_day=CHECK_DAY - timedelta(days=3))  # fmt: skip
    assert fup.state is S.CLOSED and fup.spike_day is None
    saw = _check_that_saw(check, latest_day=CHECK_DAY, deaths=400, spike=True)
    fup = _state(saw, [_answer(saw, O.BETTER)], today=CHECK_DAY + timedelta(days=4), spike_day=CHECK_DAY)
    assert fup.state is S.CLOSED and fup.spike_day is None


def test_a_check_day_spike_the_stored_input_did_not_contain_is_news():
    """The check stored fewer deaths (2) than the check-day record now has (400): it was logged after the check."""
    check = _check(Urgency.WATCH)
    assert check.input.latest_record_day == CHECK_DAY.isoformat() and check.input.deaths_latest == 2
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4), spike_day=CHECK_DAY)
    assert fup.state is S.ESCALATED and fup.spike_day == CHECK_DAY
    assert fup.reasons == (EscalationReason.RECORD_BOOK_SPIKE,) and fup.outcome is O.WORSE


def test_a_check_day_spike_is_news_when_the_check_saw_no_count_that_day_or_none_at_all():
    check = _check(Urgency.WATCH)
    for latest_day, deaths in ((CHECK_DAY - timedelta(days=1), 2), (None, None), (CHECK_DAY, None)):
        c = _check_that_saw(check, latest_day=latest_day, deaths=deaths, spike=False)
        fup = _state(c, [_answer(c, O.BETTER)], today=CHECK_DAY + timedelta(days=4), spike_day=CHECK_DAY)
        assert fup.state is S.ESCALATED and fup.spike_day == CHECK_DAY, (latest_day, deaths)


def test_a_check_day_count_equal_to_or_lower_than_the_stored_one_is_not_news():
    check = _check(Urgency.WATCH)
    for deaths in (400, 900):
        c = _check_that_saw(check, latest_day=CHECK_DAY, deaths=deaths, spike=True)
        fup = _state(c, [_answer(c, O.BETTER)], today=CHECK_DAY + timedelta(days=4), spike_day=CHECK_DAY)
        assert fup.state is S.CLOSED, deaths


def test_a_check_day_spike_does_not_count_when_there_is_no_spike_in_the_record_book():
    check = _check(Urgency.WATCH)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4))
    assert fup.state is S.CLOSED and fup.spike_day is None


def test_a_check_day_spike_after_a_same_day_vet_handoff_is_the_documented_limit():
    """Not caught by the follow-up (the separate "N birds died yesterday" briefing item still shows it)."""
    check = _check(Urgency.URGENT)
    sent_at = check.created_at + timedelta(hours=1)
    house = _house(CHECK_DAY)
    fup = follow_up_state(check, (), {check.check_id: sent_at}, house, CHECK_DAY + timedelta(days=1))
    assert fup.spike_day is None and EscalationReason.RECORD_BOOK_SPIKE not in fup.reasons


def test_a_spike_after_today_does_not_exist_yet():
    check = _check(Urgency.WATCH)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4),
                 spike_day=CHECK_DAY + timedelta(days=9))  # fmt: skip
    assert fup.state is S.CLOSED


def test_a_spike_logged_later_reopens_a_closed_follow_up():
    check = _check(Urgency.WATCH)
    answers = [_answer(check, O.BETTER)]
    spike = CHECK_DAY + timedelta(days=6)
    assert _state(check, answers, today=CHECK_DAY + timedelta(days=5), spike_day=spike).state is S.CLOSED
    assert _state(check, answers, today=CHECK_DAY + timedelta(days=6), spike_day=spike).state is S.ESCALATED


# -- a suspected reportable disease with no confirmed vet handoff never closes --------------------------------
def test_a_reportable_suspect_without_a_vet_handoff_never_closes_on_better():
    check = _check(Urgency.NOTIFIABLE_SUSPECT)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4))
    assert fup.state is S.ESCALATED and fup.outcome is O.BETTER
    assert fup.reasons == (EscalationReason.REPORTABLE_WITHOUT_VET_HANDOFF,)


def test_a_reportable_suspect_with_a_confirmed_vet_handoff_can_close_on_better():
    check = _check(Urgency.NOTIFIABLE_SUSPECT)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4), handed=[check.check_id])
    assert fup.state is S.CLOSED and fup.reasons == ()


def test_a_handoff_for_another_check_does_not_count():
    check = _check(Urgency.NOTIFIABLE_SUSPECT)
    fup = _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4), handed=[new_check_id()])
    assert fup.state is S.ESCALATED


def test_a_reportable_suspect_with_no_answer_is_asked_and_never_closed_by_the_clock():
    check = _check(Urgency.NOTIFIABLE_SUSPECT)
    assert _state(check, today=CHECK_DAY + timedelta(days=1)).state is S.DUE
    # M5 (Step 47C): it no longer lapses; with no vet handoff it stays escalated, and is never "better"
    late = _state(check, today=CHECK_DAY + timedelta(days=50))
    assert late.state is S.ESCALATED and late.outcome is None


def test_an_urgent_but_not_reportable_check_may_close_without_a_handoff():
    check = _check(Urgency.URGENT)
    assert _state(check, [_answer(check, O.BETTER)], today=CHECK_DAY + timedelta(days=4)).state is S.CLOSED


# -- the most severe answer ever given wins -------------------------------------------------------------------
def test_the_severity_order_is_better_same_not_sure_worse():
    assert sorted(O, key=fu.severity) == [O.BETTER, O.SAME, O.NOT_SURE, O.WORSE]


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ([O.WORSE, O.BETTER], O.WORSE),
        ([O.BETTER, O.WORSE], O.WORSE),
        ([O.SAME, O.NOT_SURE], O.NOT_SURE),
        ([O.NOT_SURE, O.SAME, O.BETTER], O.NOT_SURE),
        ([O.BETTER, O.BETTER], O.BETTER),
        ([O.SAME, O.WORSE, O.NOT_SURE], O.WORSE),
    ],
)
def test_the_most_severe_answer_wins_in_any_order_so_a_later_answer_cannot_lower_an_earlier_one(given, expected):
    check = _check(Urgency.URGENT)
    for perm in set(itertools.permutations(given)):
        answers = [_answer(check, said, hours=i) for i, said in enumerate(perm)]
        fup = _state(check, answers, today=CHECK_DAY + timedelta(days=4))
        assert fup.outcome is expected, perm
        assert (fup.state is S.CLOSED) == (expected is O.BETTER)


def test_a_later_better_after_worse_stays_escalated():
    check = _check(Urgency.WATCH)
    fup = _state(
        check, [_answer(check, O.WORSE), _answer(check, O.BETTER, hours=5)], today=CHECK_DAY + timedelta(days=5)
    )
    assert fup.state is S.ESCALATED and fup.outcome is O.WORSE and EscalationReason.SAID_WORSE in fup.reasons


def test_a_closed_follow_up_reopens_when_a_later_answer_is_not_better():
    check = _check(Urgency.WATCH)
    today = CHECK_DAY + timedelta(days=5)
    assert _state(check, [_answer(check, O.BETTER)], today=today).state is S.CLOSED
    assert _state(check, [_answer(check, O.BETTER), _answer(check, O.SAME, hours=2)], today=today).state is S.ESCALATED


# -- superseded -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("newer_urgency", list(Urgency))
def test_a_newer_check_on_the_house_supersedes_an_ordinary_follow_up(newer_urgency):
    old = _check(Urgency.WATCH)
    newer = _check(newer_urgency, day=CHECK_DAY + timedelta(days=1))
    # Step 38 (decision 2): an ESCALATED follow-up (for example after "worse") no longer follows this any-newer-check
    # rule; it has its own tests below. The two cases left here are the ones that are not escalated.
    for answers in ((), (_answer(old, O.BETTER),)):
        fup = _state(old, answers, today=CHECK_DAY + timedelta(days=5), others=[old, newer])
        assert fup.state is S.SUPERSEDED


def test_a_newer_check_on_another_house_or_an_older_one_supersedes_nothing():
    mid = _check(Urgency.WATCH, day=CHECK_DAY)
    elsewhere = _check(Urgency.URGENT, day=CHECK_DAY + timedelta(days=1), house_id="house-2")
    older = _check(Urgency.URGENT, day=CHECK_DAY - timedelta(days=1))
    same_day_later = _check(Urgency.URGENT, day=CHECK_DAY, hour=11)
    fup = _state(mid, today=CHECK_DAY + timedelta(days=4), others=[elsewhere, older])
    assert fup.state is S.DUE
    assert _state(mid, today=CHECK_DAY + timedelta(days=4), others=[same_day_later]).state is S.SUPERSEDED


@pytest.mark.parametrize("newer_urgency", [Urgency.ROUTINE, Urgency.WATCH, Urgency.URGENT])
def test_a_reportable_suspect_without_a_handoff_is_never_superseded_by_a_lower_check(newer_urgency):
    old = _check(Urgency.NOTIFIABLE_SUSPECT)
    newer = _check(newer_urgency, day=CHECK_DAY + timedelta(days=1))
    fup = _state(old, [_answer(old, O.BETTER)], today=CHECK_DAY + timedelta(days=5), others=[old, newer])
    assert fup.state is S.ESCALATED


def test_a_reportable_suspect_is_superseded_by_a_newer_unhanded_reportable_suspect():
    old = _check(Urgency.NOTIFIABLE_SUSPECT)
    newer = _check(Urgency.NOTIFIABLE_SUSPECT, day=CHECK_DAY + timedelta(days=1))
    assert _state(old, today=CHECK_DAY + timedelta(days=5), others=[old, newer]).state is S.SUPERSEDED


def test_a_newer_reportable_suspect_that_was_already_handed_to_a_vet_does_not_hide_the_older_one():
    old = _check(Urgency.NOTIFIABLE_SUSPECT)
    newer = _check(Urgency.NOTIFIABLE_SUSPECT, day=CHECK_DAY + timedelta(days=1))
    fup = _state(old, today=CHECK_DAY + timedelta(days=5), handed=[newer.check_id], others=[old, newer])
    assert fup.state is S.DUE


def test_a_handed_off_reportable_suspect_is_superseded_like_any_other():
    old = _check(Urgency.NOTIFIABLE_SUSPECT)
    newer = _check(Urgency.ROUTINE, day=CHECK_DAY + timedelta(days=1))
    fup = _state(
        old, [_answer(old, O.BETTER)], today=CHECK_DAY + timedelta(days=5), handed=[old.check_id], others=[newer]
    )
    assert fup.state is S.SUPERSEDED


@pytest.mark.parametrize("newer_urgency", [None, *Urgency])
@pytest.mark.parametrize("newer_handed", [False, True])
@pytest.mark.parametrize("old_handed", [False, True])
def test_superseded_matches_what_the_briefing_shows_for_a_reportable_suspect(newer_urgency, newer_handed, old_handed):
    """The follow-up must never hide a check the briefing still shows, nor outlive one it hides (design rule S13)."""
    old = _check(Urgency.NOTIFIABLE_SUSPECT)
    checks = [old]
    if newer_urgency is not None:
        checks.append(_check(newer_urgency, day=CHECK_DAY + timedelta(days=1)))
    handed = frozenset(
        ([old.check_id] if old_handed else []) + ([checks[-1].check_id] if newer_handed and len(checks) > 1 else [])
    )
    as_of = CHECK_DAY + timedelta(days=2)
    latest = max(checks, key=lambda c: c.created_at)
    shown = _check_to_show(as_of, latest, checks, handed)
    fup = follow_up_state(old, (), handed, _house(), as_of, tuple(checks))
    if old.check_id in handed:
        # handed off: the briefing has nothing to say about it; anything newer supersedes its follow-up
        assert (fup.state is S.SUPERSEDED) == (len(checks) > 1)
    else:
        assert (fup.state is not S.SUPERSEDED) == (shown is not None and shown.check_id == old.check_id)


# -- bad inputs fail loud, never guessed ----------------------------------------------------------------------
def test_an_answer_for_another_check_is_refused():
    check, other = _check(), _check()
    with pytest.raises(ValueError, match="another check"):
        _state(check, [_answer(other, O.BETTER)], today=CHECK_DAY + timedelta(days=4))


def test_a_house_record_book_for_another_house_is_refused():
    check = _check(house_id="house-1")
    with pytest.raises(ValueError, match="house"):
        follow_up_state(check, (), frozenset(), _house(house_id="house-2"), CHECK_DAY + timedelta(days=4))


def test_an_answer_needs_a_closed_list_outcome_and_a_timezone():
    check = _check()
    base = dict(answer_id=new_answer_id(), farm_id="farm", house_id="house-1", check_id=check.check_id,
                records_worse=False, proposal_id="prop_" + "b" * 16, answered_at=check.created_at)  # fmt: skip
    FollowUpAnswer(said=O.BETTER, **base)
    with pytest.raises(TypeError, match="Outcome"):
        FollowUpAnswer(said="it is fine now", **base)
    with pytest.raises(ValueError, match="timezone"):
        FollowUpAnswer(said=O.BETTER, **{**base, "answered_at": datetime(2026, 10, 13, 9, 0)})
    with pytest.raises(ValueError, match="answer_id"):
        FollowUpAnswer(said=O.BETTER, **{**base, "answer_id": "x"})
    with pytest.raises(ValueError, match="proposal_id"):
        FollowUpAnswer(said=O.BETTER, **{**base, "proposal_id": "x"})


def test_the_answer_record_has_no_free_text_field():
    from dataclasses import fields

    assert [f.name for f in fields(FollowUpAnswer)] == [
        "answer_id", "farm_id", "house_id", "check_id", "said", "records_worse", "proposal_id", "answered_at",
    ]  # fmt: skip
    assert {o.value for o in O} == {"better", "same", "worse", "not_sure"}
    assert (
        replace(_answer(_check(), O.BETTER), said=O.WORSE).said is O.WORSE
    )  # frozen dataclass: replace() builds a new one


# -- an escalated follow-up stays until an equal-or-higher newer check or a confirmed handoff ---------------------
# (it must not disappear just because any newer check exists: docs/DESIGN.md §18)
LOWER_THAN = {
    Urgency.WATCH: [Urgency.ROUTINE],
    Urgency.URGENT: [Urgency.ROUTINE, Urgency.WATCH],
    Urgency.NOTIFIABLE_SUSPECT: [Urgency.ROUTINE, Urgency.WATCH, Urgency.URGENT],
}
SAME_OR_HIGHER = {
    Urgency.WATCH: [Urgency.WATCH, Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT],
    Urgency.URGENT: [Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT],
    Urgency.NOTIFIABLE_SUSPECT: [Urgency.NOTIFIABLE_SUSPECT],
}
SPIKE_DAY = CHECK_DAY + timedelta(days=2)
TODAY = CHECK_DAY + timedelta(days=5)
# (cause, answers said, spike in the record book, urgencies it applies to)
ESCALATIONS = [
    ("worse", [O.WORSE], None, list(LOWER_THAN)),
    ("same", [O.SAME], None, list(LOWER_THAN)),
    ("not_sure", [O.NOT_SURE], None, list(LOWER_THAN)),
    ("spike_only", [], SPIKE_DAY, list(LOWER_THAN)),
    ("better_but_spike", [O.BETTER], SPIKE_DAY, list(LOWER_THAN)),
    ("better_on_a_reportable_suspect", [O.BETTER], None, [Urgency.NOTIFIABLE_SUSPECT]),
]
ESCALATION_CASES = [(u, name, said, spike) for name, said, spike, urgencies in ESCALATIONS for u in urgencies]


def _escalated(urgency, said, spike):
    check = _check(urgency)
    answers = [_answer(check, s, hours=i) for i, s in enumerate(said)]
    return check, answers, spike


@pytest.mark.parametrize(("urgency", "name", "said", "spike"), ESCALATION_CASES)
def test_a_newer_lower_urgency_check_does_not_hide_an_escalated_follow_up(urgency, name, said, spike):
    check, answers, spike_day = _escalated(urgency, said, spike)
    alone = _state(check, answers, today=TODAY, spike_day=spike_day, others=[check])
    assert alone.state is S.ESCALATED
    for lower in LOWER_THAN[urgency]:
        newer = _check(lower, day=CHECK_DAY + timedelta(days=1))
        fup = _state(check, answers, today=TODAY, spike_day=spike_day, others=[check, newer])
        assert fup == alone, (name, lower)  # not one field changes: same state, outcome and reasons


@pytest.mark.parametrize(("urgency", "name", "said", "spike"), ESCALATION_CASES)
def test_a_newer_check_of_equal_or_higher_urgency_replaces_an_escalated_follow_up(urgency, name, said, spike):
    check, answers, spike_day = _escalated(urgency, said, spike)
    for level in SAME_OR_HIGHER[urgency]:
        newer = _check(level, day=CHECK_DAY + timedelta(days=1))
        fup = _state(check, answers, today=TODAY, spike_day=spike_day, others=[check, newer])
        assert fup.state is S.SUPERSEDED, (name, level)


@pytest.mark.parametrize(("urgency", "name", "said", "spike"), ESCALATION_CASES)
def test_one_higher_check_among_lower_ones_is_enough(urgency, name, said, spike):
    check, answers, spike_day = _escalated(urgency, said, spike)
    newer = [_check(u, day=CHECK_DAY + timedelta(days=1 + i)) for i, u in enumerate(LOWER_THAN[urgency])]
    assert _state(check, answers, today=TODAY, spike_day=spike_day, others=[check, *newer]).state is S.ESCALATED
    same = _check(urgency, day=CHECK_DAY + timedelta(days=4))
    assert _state(check, answers, today=TODAY, spike_day=spike_day, others=[check, *newer, same]).state is S.SUPERSEDED


# "better" on a reportable suspect escalates only while no vet handoff exists; once one does it simply closes (rule S4,
# tested above), so that case is not an escalated follow-up to end.
HANDOFF_CASES = [c for c in ESCALATION_CASES if c[1] != "better_on_a_reportable_suspect"]


@pytest.mark.parametrize(("urgency", "name", "said", "spike"), HANDOFF_CASES)
def test_a_confirmed_vet_handoff_for_that_check_ends_an_escalated_follow_up(urgency, name, said, spike):
    check, answers, spike_day = _escalated(urgency, said, spike)
    without = _state(check, answers, today=TODAY, spike_day=spike_day)
    assert without.state is S.ESCALATED
    handed = _state(check, answers, today=TODAY, spike_day=spike_day, handed=[check.check_id])
    assert handed.state is S.SUPERSEDED  # a vet handoff takes it over: nothing left to escalate
    assert handed.urgency is urgency  # and nothing was lowered
    other = _state(check, answers, today=TODAY, spike_day=spike_day, handed=[new_check_id()])
    assert other.state is S.ESCALATED  # a handoff for some other check does not count


def test_a_newer_check_on_another_house_or_an_older_check_never_hides_an_escalated_follow_up():
    check = _check(Urgency.WATCH)
    answers = [_answer(check, O.WORSE)]
    elsewhere = _check(Urgency.NOTIFIABLE_SUSPECT, day=CHECK_DAY + timedelta(days=1), house_id="house-2")
    older = _check(Urgency.NOTIFIABLE_SUSPECT, day=CHECK_DAY - timedelta(days=1))
    assert _state(check, answers, today=TODAY, others=[check, elsewhere, older]).state is S.ESCALATED


def test_a_follow_up_that_is_not_escalated_is_still_replaced_by_any_newer_check():
    """The scope of decision 2: only an escalated follow-up is protected. Due, scheduled, lapsed and closed
    follow-ups are still replaced by any newer check on the house."""
    old = _check(Urgency.WATCH)
    newer = _check(Urgency.ROUTINE, day=CHECK_DAY + timedelta(days=1))
    for today in (CHECK_DAY + timedelta(days=1), CHECK_DAY + timedelta(days=4), CHECK_DAY + timedelta(days=40)):
        assert _state(old, today=today, others=[old, newer]).state is S.SUPERSEDED
    assert _state(old, [_answer(old, O.BETTER)], today=TODAY, others=[old, newer]).state is S.SUPERSEDED


def test_a_newer_lower_check_never_lowers_the_urgency_the_follow_up_reports():
    check = _check(Urgency.URGENT)
    newer = _check(Urgency.ROUTINE, day=CHECK_DAY + timedelta(days=1))
    fup = _state(check, [_answer(check, O.WORSE)], today=TODAY, others=[check, newer])
    assert fup.state is S.ESCALATED and fup.urgency is Urgency.URGENT


# -- the spike is the briefing's own definition: same shed, only days after the check -------------------------------
def test_the_spike_is_found_with_the_same_function_the_briefing_and_status_use():
    from clucktalk.domain import status

    assert fu.spike_finding is status.spike_finding  # one definition of "a death spike", not a second copy


def test_the_follow_up_sees_a_spike_exactly_when_the_status_finding_does():
    from clucktalk.domain.status import house_status

    check = _check(Urgency.WATCH)
    for day_of_spike in (CHECK_DAY + timedelta(days=1), CHECK_DAY + timedelta(days=4)):
        house = _house(day_of_spike)
        finding_codes = {f.code for f in house_status(house, day_of_spike).findings}
        assert "mortality_spike" in finding_codes  # the status sees the spike on its own day
        fup = follow_up_state(check, (), frozenset(), house, day_of_spike, ())
        assert fup.spike_day == day_of_spike and fup.state is S.ESCALATED
    quiet = _house(None)
    assert "mortality_spike" not in {f.code for f in house_status(quiet, TODAY).findings}
    assert follow_up_state(check, (), frozenset(), quiet, TODAY, ()).spike_day is None


def test_only_days_after_the_check_and_up_to_today_count():
    # the check stored the check-day count with the spike in it (H2: otherwise that day is news, see above)
    check = _check_that_saw(_check(Urgency.WATCH), latest_day=CHECK_DAY, deaths=400, spike=True)
    for spike_day, today, seen in [
        (CHECK_DAY - timedelta(days=1), TODAY, False),
        (CHECK_DAY, TODAY, False),  # the day of the check: it is what the check was about
        (CHECK_DAY + timedelta(days=1), TODAY, True),
        (TODAY, TODAY, True),
        (TODAY + timedelta(days=1), TODAY, False),  # not yet happened
    ]:
        got = follow_up_state(check, (), frozenset(), _house(spike_day), today, ()).spike_day
        assert (got is not None) == seen, (spike_day, today)


# -- an answer is taken from the day after the check -----------------------------------------------
def test_an_answer_is_only_accepted_from_the_day_after_the_check():
    check = _check(Urgency.WATCH)
    assert fu.answerable(check, CHECK_DAY) is False  # the day of the check: nothing to compare with yet
    assert fu.answerable(check, CHECK_DAY - timedelta(days=1)) is False
    assert fu.answerable(check, CHECK_DAY + timedelta(days=1)) is True
    assert fu.answerable(check, CHECK_DAY + timedelta(days=90)) is True


# -- a vet handoff ends what came before it, not what comes after it -------------------------------
# After a handoff for a check, "worse", "same", "not sure" or a new death spike escalates again; "better" only closes.
HANDOFF_AT = datetime.combine(CHECK_DAY + timedelta(days=3), dtime(12, 0), tzinfo=IST)
BEFORE_HANDOFF = HANDOFF_AT - timedelta(hours=2)
AFTER_HANDOFF = HANDOFF_AT + timedelta(hours=2)
LATER_AFTER_HANDOFF = HANDOFF_AT + timedelta(hours=5)
HANDED_TODAY = CHECK_DAY + timedelta(days=5)
ALL_LEVELS = [Urgency.WATCH, Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT]


def _said_at(check, said, at):
    return FollowUpAnswer(
        new_answer_id(), check.farm_id, check.house_id, check.check_id, said, False, "prop_" + "a" * 16, at
    )


def _handed(check, answers, *, today=HANDED_TODAY, spike_day=None, others=(), handed_at=HANDOFF_AT):
    return follow_up_state(check, tuple(answers), {check.check_id: handed_at}, _house(spike_day), today, tuple(others))


@pytest.mark.parametrize("urgency", ALL_LEVELS)
@pytest.mark.parametrize("said", [O.SAME, O.WORSE, O.NOT_SURE])
def test_not_better_after_the_handoff_escalates_again(urgency, said):
    check = _check(urgency)
    fup = _handed(check, [_said_at(check, said, AFTER_HANDOFF)])
    assert fup.state is S.ESCALATED and fup.handed_off is True and fup.outcome is said
    assert fup.reasons == (
        EscalationReason(f"said_{said.value}"),
    )  # the handoff is done: no reportable-without-handoff
    assert fup.urgency is urgency


@pytest.mark.parametrize("urgency", ALL_LEVELS)
def test_answers_given_before_the_handoff_are_handled_by_it(urgency):
    check = _check(urgency)
    for said in (O.SAME, O.WORSE, O.NOT_SURE):
        fup = _handed(check, [_said_at(check, said, BEFORE_HANDOFF)])
        assert fup.state is S.SUPERSEDED and fup.handed_off is True and fup.reasons == ()


@pytest.mark.parametrize("urgency", ALL_LEVELS)
def test_better_after_the_handoff_is_accepted_and_only_closes(urgency):
    check = _check(urgency)
    only = _handed(check, [_said_at(check, O.BETTER, AFTER_HANDOFF)])
    assert only.state is S.CLOSED and only.outcome is O.BETTER and only.reasons == () and only.urgency is urgency
    after_worse = _handed(check, [_said_at(check, O.WORSE, BEFORE_HANDOFF), _said_at(check, O.BETTER, AFTER_HANDOFF)])
    assert after_worse.state is S.CLOSED and after_worse.outcome is O.BETTER and after_worse.handed_off is True


def test_after_the_handoff_the_most_severe_new_answer_still_wins():
    check = _check(Urgency.URGENT)
    for first, second in ((O.WORSE, O.BETTER), (O.BETTER, O.WORSE)):
        answers = [_said_at(check, first, AFTER_HANDOFF), _said_at(check, second, LATER_AFTER_HANDOFF)]
        fup = _handed(check, answers)
        assert fup.state is S.ESCALATED and fup.outcome is O.WORSE


def test_an_answer_at_the_very_instant_of_the_handoff_counts_as_before_it():
    check = _check(Urgency.URGENT)
    fup = _handed(check, [_said_at(check, O.WORSE, HANDOFF_AT)])
    assert fup.state is S.SUPERSEDED  # the usual order is the answer first, then the handoff it led to


def test_a_death_spike_on_a_day_after_the_handoff_escalates_again_but_not_one_before_it():
    check = _check(Urgency.URGENT)
    handoff_day = HANDOFF_AT.date()
    after = _handed(check, [], spike_day=handoff_day + timedelta(days=1))
    assert after.state is S.ESCALATED and after.reasons == (EscalationReason.RECORD_BOOK_SPIKE,)
    assert after.spike_day == handoff_day + timedelta(days=1)
    for day in (handoff_day, handoff_day - timedelta(days=1)):  # the spike the handoff was already about
        before = _handed(check, [], spike_day=day)
        assert before.state is S.SUPERSEDED and before.spike_day is None


def test_better_after_the_handoff_is_not_undone_by_a_spike_from_before_it():
    check = _check(Urgency.URGENT)
    fup = _handed(check, [_said_at(check, O.BETTER, AFTER_HANDOFF)], spike_day=HANDOFF_AT.date() - timedelta(days=1))
    assert fup.state is S.CLOSED


@pytest.mark.parametrize("urgency", ALL_LEVELS)
def test_an_escalation_after_a_handoff_is_hidden_only_by_a_newer_check_of_equal_or_higher_urgency(urgency):
    check = _check(urgency)
    answers = [_said_at(check, O.WORSE, AFTER_HANDOFF)]
    for lower in LOWER_THAN[urgency]:
        newer = _check(lower, day=CHECK_DAY + timedelta(days=1))
        fup = _handed(check, answers, others=[check, newer])
        assert fup.state is S.ESCALATED and fup.handed_off is True, lower
    for level in SAME_OR_HIGHER[urgency]:
        newer = _check(level, day=CHECK_DAY + timedelta(days=1))
        assert _handed(check, answers, others=[check, newer]).state is S.SUPERSEDED, level


def test_a_handed_off_follow_up_with_no_new_evidence_still_follows_the_clock():
    check = _check(Urgency.WATCH)
    due_day = CHECK_DAY + timedelta(days=3)
    assert _handed(check, [], today=due_day - timedelta(days=1)).state is S.SCHEDULED
    assert _handed(check, [], today=due_day).state is S.DUE
    assert _handed(check, [], today=due_day).handed_off is True


def test_a_handoff_with_no_time_known_ends_the_escalation_for_good():
    """Ids alone (no send time): everything on file is taken as before the handoff (the earlier, simpler rule)."""
    check = _check(Urgency.URGENT)
    fup = follow_up_state(
        check, [_said_at(check, O.WORSE, AFTER_HANDOFF)], frozenset([check.check_id]), _house(), TODAY
    )
    assert fup.state is S.SUPERSEDED and fup.handed_off is True


def test_the_handed_off_flag_is_false_without_a_handoff_and_the_check_day_is_always_given():
    check = _check(Urgency.WATCH)
    plain = _state(check, today=TODAY)
    assert plain.handed_off is False and plain.check_day == CHECK_DAY
    other = follow_up_state(check, (), {new_check_id(): HANDOFF_AT}, _house(), TODAY)
    assert other.handed_off is False  # a handoff for some other check
    assert _state(_check(Urgency.ROUTINE), today=TODAY).check_day == CHECK_DAY


def test_both_forms_of_handed_off_are_accepted_and_agree_when_no_answers_exist():
    check = _check(Urgency.URGENT)
    as_ids = follow_up_state(check, (), frozenset([check.check_id]), _house(), TODAY)
    as_times = follow_up_state(check, (), {check.check_id: HANDOFF_AT}, _house(), TODAY)
    assert as_ids == as_times


def test_how_long_until_a_follow_up_is_due_comes_from_the_named_windows():
    assert fu.due_after_days(Urgency.WATCH) == fu.FOLLOW_UP_AFTER_WATCH_DAYS
    assert fu.due_after_days(Urgency.URGENT) == fu.FOLLOW_UP_AFTER_URGENT_DAYS
    assert fu.due_after_days(Urgency.NOTIFIABLE_SUSPECT) == fu.FOLLOW_UP_AFTER_URGENT_DAYS
    assert fu.due_after_days(Urgency.ROUTINE) is None
    check = _check(Urgency.WATCH)
    assert _state(check, today=TODAY).due_day == CHECK_DAY + timedelta(days=fu.due_after_days(Urgency.WATCH))
