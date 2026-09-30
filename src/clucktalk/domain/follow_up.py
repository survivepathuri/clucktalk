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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from clucktalk.domain.models import House
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
    spike_day: date | None  # the latest death-spike day after the check, if any


def _told_urgency(check: HealthCheck) -> Urgency:
    """What the farmer was told: the model's answer, or (still running, or it could not answer) the code floor. The
    same rule as the briefing's ``check_urgency`` (a test keeps the two equal; the briefing imports this module
    later, so this cannot import it)."""
    return check.result.urgency if check.result is not None else check.floor.urgency


def _unhanded_reportable(check: HealthCheck, handed_off: frozenset[str]) -> bool:
    return _told_urgency(check) is Urgency.NOTIFIABLE_SUSPECT and check.check_id not in handed_off


def _superseded(check: HealthCheck, handed_off: frozenset[str], house_checks: Sequence[HealthCheck]) -> bool:
    """Any newer check on the house takes over, except that a suspected reportable disease not yet handed to a vet is
    taken over only by a newer one of its own kind (the same rule as the briefing's ``_check_to_show``)."""
    newer = [
        c
        for c in house_checks
        if c.farm_id == check.farm_id and c.house_id == check.house_id and c.created_at > check.created_at
    ]
    if _unhanded_reportable(check, handed_off):
        return any(_unhanded_reportable(c, handed_off) for c in newer)
    return bool(newer)


def _latest_spike_after(house: House, check_day: date, today: date) -> date | None:
    records = house.records_until(today)
    for rec in reversed(records):
        if rec.day <= check_day:
            break
        if spike_finding(house, records, rec) is not None:
            return rec.day
    return None


def follow_up_state(
    check: HealthCheck,
    answers: Sequence[FollowUpAnswer],
    handed_off: frozenset[str],
    house: House,
    today: date,
    house_checks: Sequence[HealthCheck] = (),
) -> FollowUp:
    """The state of ``check``'s follow-up on ``today``.

    ``answers``: every stored answer for this check. ``handed_off``: ids of checks with a confirmed vet handoff.
    ``house``: this house with its record book (logged records already overlaid). ``house_checks``: this house's
    checks (may include ``check`` itself), to find a newer one. Checked in this order: none, superseded, escalated,
    closed, then the clock alone (scheduled, due, lapsed)."""
    if house.house_id != check.house_id:
        raise ValueError(f"the record book is for {house.house_id}, the check is for {check.house_id}: wrong house")
    for a in answers:
        if a.check_id != check.check_id:
            raise ValueError(f"answer {a.answer_id} belongs to another check")

    urgency = _told_urgency(check)
    if check.status is CheckStatus.ANALYZING or urgency < Urgency.WATCH:
        return FollowUp(FollowUpState.NONE, check.check_id, urgency, None, None, (), None)

    check_day = check.created_at.date()
    wait = FOLLOW_UP_AFTER_URGENT_DAYS if urgency >= Urgency.URGENT else FOLLOW_UP_AFTER_WATCH_DAYS
    due_day = check_day + timedelta(days=wait)

    if _superseded(check, handed_off, house_checks):
        return FollowUp(FollowUpState.SUPERSEDED, check.check_id, urgency, due_day, None, (), None)

    said = max((a.said for a in answers), key=severity, default=None)
    spike_day = _latest_spike_after(house, check_day, today)
    outcome = Outcome.WORSE if spike_day is not None else said  # a spike counts as worse, whatever was said

    reasons: list[EscalationReason] = []
    if said in _SAID_REASON:
        reasons.append(_SAID_REASON[said])
    if spike_day is not None:
        reasons.append(EscalationReason.RECORD_BOOK_SPIKE)
    if answers and _unhanded_reportable(check, handed_off):
        reasons.append(EscalationReason.REPORTABLE_WITHOUT_VET_HANDOFF)

    if reasons:
        return FollowUp(FollowUpState.ESCALATED, check.check_id, urgency, due_day, outcome, tuple(reasons), spike_day)
    if answers:  # only "better" answers, no spike, nothing still owed to a vet
        return FollowUp(FollowUpState.CLOSED, check.check_id, urgency, due_day, Outcome.BETTER, (), None)
    if today < due_day:
        state = FollowUpState.SCHEDULED
    elif today <= due_day + timedelta(days=FOLLOW_UP_LAPSE_AFTER_DUE_DAYS):
        state = FollowUpState.DUE
    else:
        state = FollowUpState.LAPSED
    return FollowUp(state, check.check_id, urgency, due_day, None, (), None)
