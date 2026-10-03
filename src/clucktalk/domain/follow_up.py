"""Flock follow-up: what the farm should ask about, days after a health check flagged a shed (docs/DESIGN.md §18).

The state of a follow-up is a pure function of the stored health check, the farmer's stored answers, the confirmed vet
handoffs, the house's record book and the date passed in as ``today``. No I/O, no model call, and no clock of its own:
the caller injects the date (a real one, or a test's, or later a labelled demo clock). The only thing ever stored is
an answer; everything else is derived on every read, so a restart cannot lose or change it.

Safety (design rules S1-S5, S9, S13): an answer never lowers or clears a check's urgency (``better`` only closes the
follow-up); ``same``, ``worse`` and ``not_sure`` escalate; a death spike in the record book after the check counts as
``worse`` whatever was said; a suspected reportable disease with no confirmed vet handoff never closes; the most
severe answer ever given wins; no answer is never ``better``. Escalation reasons are codes, never sentences.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from clucktalk.domain.models import DailyRecord, House
from clucktalk.domain.proposals import PROPOSAL_ID_PATTERN
from clucktalk.domain.status import spike_finding
from clucktalk.domain.triage import CheckStatus, HealthCheck, Urgency

# The follow-up time windows. They are our own rules, not sourced figures: no veterinary source gives "ask again
# after N days", so they must never be presented as guidance from one. They are defined here and nowhere else (a
# test enforces it); change a window here only.
FOLLOW_UP_AFTER_WATCH_DAYS = 3  # a "watch" check is asked about again this many days later
FOLLOW_UP_AFTER_URGENT_DAYS = 1  # an "urgent" check, or a suspected reportable disease: the next day
FOLLOW_UP_LAPSE_AFTER_DUE_DAYS = 7  # still asked for this many days after it was due; then it lapses (never "better")

ANSWER_ID_PATTERN = r"^fu_[0-9a-f]{16}$"


class Outcome(StrEnum):
    """What the farmer says about the shed now. A closed list: there is no free-text answer."""

    BETTER = "better"
    SAME = "same"
    WORSE = "worse"
    NOT_SURE = "not_sure"


_SEVERITY = {Outcome.BETTER: 0, Outcome.SAME: 1, Outcome.NOT_SURE: 2, Outcome.WORSE: 3}


def severity(outcome: Outcome) -> int:
    """Order of concern: better < same < not sure < worse."""
    return _SEVERITY[outcome]


class FollowUpState(StrEnum):
    NONE = "none"
    SCHEDULED = "scheduled"
    DUE = "due"
    CLOSED = "closed"
    ESCALATED = "escalated"
    SUPERSEDED = "superseded"
    LAPSED = "lapsed"


class EscalationReason(StrEnum):
    """Why a follow-up escalated. Stable codes for structuredContent and tests; never spoken."""

    SAID_SAME = "said_same"
    SAID_WORSE = "said_worse"
    SAID_NOT_SURE = "said_not_sure"
    RECORD_BOOK_SPIKE = "record_book_spike"
    # No confirmed vet handoff for a check that needs one: a reportable suspect that was answered, or an urgent or
    # reportable check still unanswered after the 7-day window (one code, so the stable list is unchanged).
    REPORTABLE_WITHOUT_VET_HANDOFF = "reportable_without_vet_handoff"


_SAID_REASON = {
    Outcome.SAME: EscalationReason.SAID_SAME,
    Outcome.WORSE: EscalationReason.SAID_WORSE,
    Outcome.NOT_SURE: EscalationReason.SAID_NOT_SURE,
}


def new_answer_id() -> str:
    return "fu_" + secrets.token_hex(8)


@dataclass(frozen=True)
class FollowUpAnswer:
    """One confirmed answer (saved only after the farmer's "yes"). Append-only: never edited, never deleted."""

    answer_id: str
    farm_id: str
    house_id: str
    check_id: str
    said: Outcome
    records_worse: bool  # the record book's own verdict when the answer was saved (audit only; re-derived on read)
    proposal_id: str  # the confirmed proposal that saved it
    answered_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.said, Outcome):
            raise TypeError(f"said must be an Outcome, not {type(self.said).__name__}")
        if not re.fullmatch(ANSWER_ID_PATTERN, self.answer_id):
            raise ValueError(f"answer_id {self.answer_id!r} is not an answer id")
        if not re.fullmatch(PROPOSAL_ID_PATTERN, self.proposal_id):
            raise ValueError(f"proposal_id {self.proposal_id!r} is not a proposal id")
        if self.answered_at.tzinfo is None:
            raise ValueError("answered_at must carry a timezone")


@dataclass(frozen=True)
class FollowUp:
    state: FollowUpState
    check_id: str
    urgency: Urgency  # what the farmer was told about the check: never changed by any answer
    due_day: date | None
    outcome: Outcome | None  # the effective answer: the most severe one given, or worse if the record book says so
    reasons: tuple[EscalationReason, ...]
    spike_day: date | None  # the latest death-spike day after the check (and after the handoff, if one was sent)
    handed_off: bool = False  # a vet handoff for this check was confirmed
    check_day: date | None = None  # the day of the check, so "N days ago" always comes from the date passed in


def due_after_days(urgency: Urgency) -> int | None:
    """Days after a check of this urgency until its follow-up is due; None for a routine check (it has none)."""
    if urgency >= Urgency.URGENT:
        return FOLLOW_UP_AFTER_URGENT_DAYS
    if urgency >= Urgency.WATCH:
        return FOLLOW_UP_AFTER_WATCH_DAYS
    return None


def _told_urgency(check: HealthCheck) -> Urgency:
    """What the farmer was told: the model's answer, or (still running, or it could not answer) the code floor. The
    same rule as the briefing's ``check_urgency`` (a test keeps the two equal; the briefing imports this module
    later, so this cannot import it)."""
    return check.result.urgency if check.result is not None else check.floor.urgency


HandedOff = Collection[str] | Mapping[str, datetime]  # check ids with a confirmed handoff, or id -> when it was sent


def _unhanded_reportable(check: HealthCheck, handed_off: HandedOff) -> bool:
    return _told_urgency(check) is Urgency.NOTIFIABLE_SUSPECT and check.check_id not in handed_off


def _superseded(
    check: HealthCheck,
    urgency: Urgency,
    escalated: bool,
    handed_off: HandedOff,
    house_checks: Sequence[HealthCheck],
) -> bool:
    """When another check takes the follow-up over.

    An ESCALATED follow-up does not disappear because some newer check exists: it stays until a newer check on the
    house of equal or higher urgency exists (decided 2026-10-01; a newer check that is LOWER in urgency never hides it).
    The same holds for any follow-up of an URGENT check, escalated or not (review finding H3, approved 2026-10-01): a
    newer check of lower urgency never hides it; it ends by "better", a newer check of equal or higher urgency, the
    vet handoff, or the 7-day lapse. A vet handoff for the check does not hide an escalation either, because
    ``follow_up_state`` only lets what came AFTER the handoff escalate. Any other follow-up (a watch check's) is taken
    over by any newer check on the house, except that a suspected reportable disease not yet handed to a vet is taken
    over only by a newer one of its own kind (the briefing's ``_check_to_show`` rule, which changes together with
    this one)."""
    newer = [
        c
        for c in house_checks
        if c.farm_id == check.farm_id and c.house_id == check.house_id and c.created_at > check.created_at
    ]
    if escalated:
        return any(_told_urgency(c) >= urgency for c in newer)
    if _unhanded_reportable(check, handed_off):
        return any(_unhanded_reportable(c, handed_off) for c in newer)
    # an urgent check: only a newer check of equal or higher urgency takes it over; a confirmed vet handoff ends it
    if urgency >= Urgency.URGENT and check.check_id not in handed_off:
        return any(_told_urgency(c) >= urgency for c in newer)
    return bool(newer)


def answerable(check: HealthCheck, today: date) -> bool:
    """An answer is taken from the day after the check. On the day itself there is nothing to compare with, and a
    same-day "better" must not close a follow-up that was never asked."""
    return today > check.created_at.date()


def _check_day_record_is_news(check: HealthCheck, rec: DailyRecord) -> bool:
    """Is the record of the CHECK's own day something the check did not know? The check stores the latest count it saw
    (``latest_record_day``, ``deaths_latest``). The record is news when the check saw no count for that day, or saw
    fewer deaths than the record has now: it was logged, or raised, after the check (review finding H2)."""
    seen = check.input
    if seen.latest_record_day != rec.day.isoformat() or seen.deaths_latest is None:
        return True
    return rec.deaths > seen.deaths_latest


def _latest_spike_after(house: House, check: HealthCheck, today: date) -> date | None:
    """The latest day after the check with a death spike; the check's own day counts only if it is news. A spike on
    an earlier day is not news. (After a same-day vet handoff the day is not counted: see ``follow_up_state``.)"""
    check_day = check.created_at.date()
    records = house.records_until(today)
    for rec in reversed(records):
        if rec.day < check_day:
            break
        if rec.day == check_day and not _check_day_record_is_news(check, rec):
            break
        if spike_finding(house, records, rec) is not None:
            return rec.day
    return None


def _unanswered_past_lapse(urgency: Urgency, handed: bool, answered: bool, due_day: date, today: date) -> bool:
    """Review finding M5: an urgent check or a suspected reportable disease that nobody answered and that has no
    confirmed vet handoff does not lapse silently once the 7-day window ends; it stays escalated until an answer
    closes it, a vet handoff is confirmed, or a newer check of equal or higher urgency takes it over. A watch check's
    follow-up keeps the lapse. The one place this rule lives; the briefing, the farm status and the cards read the
    state it produces."""
    past_lapse = today > due_day + timedelta(days=FOLLOW_UP_LAPSE_AFTER_DUE_DAYS)
    return urgency >= Urgency.URGENT and not handed and not answered and past_lapse


def follow_up_state(
    check: HealthCheck,
    answers: Sequence[FollowUpAnswer],
    handed_off: HandedOff,
    house: House,
    today: date,
    house_checks: Sequence[HealthCheck] = (),
) -> FollowUp:
    """The state of ``check``'s follow-up on ``today``.

    ``answers``: every stored answer for this check. ``handed_off``: the checks with a confirmed vet handoff, either
    their ids alone (then everything on file counts as before the handoff) or id -> when it was sent (then only an
    answer given, or a death spike on a day, AFTER it can escalate again). ``house``: this house with its record book
    (logged records already overlaid). ``house_checks``: this house's checks (may include ``check`` itself), to find a
    newer one. Checked in this order: none; whether it is escalated (an answer, a death spike, a reportable disease
    with no handoff); superseded (see ``_superseded``, which depends on escalation); escalated; closed; then the clock
    alone (scheduled, due, lapsed).

    A vet handoff ends what came before it: the follow-up shows as superseded ("handled") until something new is said
    or logged. A "worse", "same" or "not sure" after it escalates again; a "better" after it only closes."""
    if house.house_id != check.house_id:
        raise ValueError(f"the record book is for {house.house_id}, the check is for {check.house_id}: wrong house")
    for a in answers:
        if a.check_id != check.check_id:
            raise ValueError(f"answer {a.answer_id} belongs to another check")

    urgency = _told_urgency(check)
    check_day = check.created_at.date()
    handed = check.check_id in handed_off
    wait = due_after_days(urgency)
    if check.status is CheckStatus.ANALYZING or wait is None:
        return FollowUp(FollowUpState.NONE, check.check_id, urgency, None, None, (), None, handed, check_day)
    due_day = check_day + timedelta(days=wait)

    spike_day = _latest_spike_after(house, check, today)
    sent_at = handed_off.get(check.check_id) if isinstance(handed_off, Mapping) else None
    if handed:
        # What can escalate now: only what came after the handoff. With no send time known, nothing did.
        live = tuple(a for a in answers if sent_at is not None and a.answered_at > sent_at)
        live_spike = spike_day if sent_at is not None and spike_day is not None and spike_day > sent_at.date() else None
    else:
        live, live_spike = tuple(answers), spike_day

    said = max((a.said for a in live), key=severity, default=None)
    outcome = Outcome.WORSE if live_spike is not None else said  # a spike counts as worse, whatever was said

    reasons: list[EscalationReason] = []
    if said in _SAID_REASON:
        reasons.append(_SAID_REASON[said])
    if live_spike is not None:
        reasons.append(EscalationReason.RECORD_BOOK_SPIKE)
    if answers and _unhanded_reportable(check, handed_off):
        reasons.append(EscalationReason.REPORTABLE_WITHOUT_VET_HANDOFF)
    if _unanswered_past_lapse(urgency, handed, bool(answers), due_day, today):
        reasons.append(EscalationReason.REPORTABLE_WITHOUT_VET_HANDOFF)  # the one code for "still needs a vet"

    def done(state: FollowUpState, out: Outcome | None, why: tuple[EscalationReason, ...], spike: date | None):
        return FollowUp(state, check.check_id, urgency, due_day, out, why, spike, handed, check_day)

    if _superseded(check, urgency, bool(reasons), handed_off, house_checks):
        return done(FollowUpState.SUPERSEDED, None, (), None)
    if reasons:
        return done(FollowUpState.ESCALATED, outcome, tuple(reasons), live_spike)
    if handed:  # no live evidence: what is on file either was handled by the handoff, or is only "better"
        if live:
            return done(FollowUpState.CLOSED, Outcome.BETTER, (), None)  # "better" after a handoff only closes
        earlier = [a.said for a in answers]
        if (earlier and max(earlier, key=severity) in _SAID_REASON) or spike_day is not None:
            return done(FollowUpState.SUPERSEDED, None, (), None)  # handled by the vet handoff
    if answers:  # only "better" answers, no spike, nothing still owed to a vet
        return done(FollowUpState.CLOSED, Outcome.BETTER, (), None)
    if today < due_day:
        state = FollowUpState.SCHEDULED
    elif today <= due_day + timedelta(days=FOLLOW_UP_LAPSE_AFTER_DUE_DAYS):
        state = FollowUpState.DUE
    else:
        state = FollowUpState.LAPSED
    return done(state, None, (), None)
