"""``report_health_follow_up``: the farmer says how a shed that had a health check is doing now (docs/DESIGN.md §5.1,
§7 rule 3, §18).

Follows the one confirmation pattern (§5.1): the first call reads the answer back and saves nothing; only an explicit
"yes" (the same call plus ``proposal_id`` and ``answer``) saves it, as one appended row. The follow-up's state is
worked out by ``clucktalk.domain.follow_up`` from stored data and the day (no model, nothing slow): this tool only
reads, asks, and appends the farmer's confirmed answer.

Safety: an answer never lowers or clears a health check's urgency ("better" only closes the follow-up). "Same",
"worse", "not sure", or a death spike in the record book since the check escalate in wording ("To be safe, contact
your vet or doctor") and offer the existing ``prepare_vet_handoff``, which stays a separate step with its own "yes";
this tool never sends anything. No medicine, dose, sample, lab, reassurance or rearing advice, and no free-text
argument. Telugu: review status per string in docs/TELUGU_REVIEW.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict

from clucktalk.domain.briefing import NOTIFIABLE_DAYS, Fact, check_urgency, health_fact
from clucktalk.domain.errors import DomainError, NoHealthCheck
from clucktalk.domain.follow_up import (
    FollowUp,
    FollowUpAnswer,
    FollowUpState,
    Outcome,
    answerable,
    follow_up_state,
    new_answer_id,
)
from clucktalk.domain.houses import resolve_house
from clucktalk.domain.models import House
from clucktalk.domain.proposals import PROPOSAL_TTL, Answer, Proposal, ProposalId, ProposalStatus
from clucktalk.domain.triage import HealthCheck, Urgency
from clucktalk.i18n import Text
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import num, plural
from clucktalk.server.tools import Capability, CapabilityRegistry
from clucktalk.server.tools.health import (
    ANSWER_PARAM,
    CHECK_PARAM,
    HOUSE_PARAM,
    OFFER,
    PROPOSAL_PARAM,
    URGENCY_SHORT,
    CheckId,
    _effective,
)
from clucktalk.server.tools.profile import DONE, KEPT, REASON_TEXT

TOOL = "report_health_follow_up"
OutcomeName = Literal["better", "same", "worse", "not_sure"]
assert set(OutcomeName.__args__) == {o.value for o in Outcome}  # the schema enum and the domain stay one list

# -- every sentence the tool speaks (plus DONE, KEPT, REASON_TEXT and OFFER, reused as they are) --------------------
TO_BE_SAFE = Text("To be safe, contact your vet or doctor.", "జాగ్రత్త కోసం, మీ డాక్టర్‌కి ఫోన్ చేయండి.")


def _spike_note(n: str) -> Text:
    return Text(
        f"The record book shows a death spike of {n} deaths since the health check, so I'll record this as not better.",
        f"ఆరోగ్య తనిఖీ తర్వాత రికార్డ్ బుక్‌లో {n} మరణాల పెరుగుదల కనిపిస్తోంది, కాబట్టి దీన్ని 'మెరుగ్గా లేదు' అని నమోదు చేస్తాను.",
    )


def _ask(outcome: Outcome, label: Text) -> Text:
    """The read-back: what will be saved, then the yes/no question."""
    match outcome:
        case Outcome.BETTER:
            return Text(
                f"I'll note this for {label.en}: the birds are better. "
                "Say yes to save it, or no to keep things as they are.",
                f"{label.te} కోసం ఇది నమోదు చేస్తాను: కోళ్లు మెరుగ్గా ఉన్నాయి. సేవ్ చేయాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
            )
        case Outcome.SAME:
            return Text(
                f"I'll note this for {label.en}: the birds are the same. "
                "Say yes to save it, or no to keep things as they are.",
                f"{label.te} కోసం ఇది నమోదు చేస్తాను: కోళ్లు అలాగే ఉన్నాయి. సేవ్ చేయాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
            )
        case Outcome.WORSE:
            return Text(
                f"I'll note this for {label.en}: the birds are worse. "
                "Say yes to save it, or no to keep things as they are.",
                f"{label.te} కోసం ఇది నమోదు చేస్తాను: కోళ్లు మరింత అధ్వాన్నంగా ఉన్నాయి. సేవ్ చేయాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
            )
        case Outcome.NOT_SURE:
            return Text(
                f"I'll note this for {label.en}: you're not sure how the birds are. "
                "Say yes to save it, or no to keep things as they are.",
                f"{label.te} కోసం ఇది నమోదు చేస్తాను: కోళ్లు ఎలా ఉన్నాయో మీకు తెలియడం లేదు. సేవ్ చేయాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
            )


class NothingToFollowUp(DomainError):
    """No health check is waiting for this answer: none needs one, it is not yet the day after the check, it was
    replaced or already closed. The next step is the existing "tell me the signs" one (reused, not copied)."""

    def __init__(self, label_en: str, label_te: str) -> None:
        reused = NoHealthCheck(label_en, label_te)
        super().__init__(
            f"There's no health check waiting for a follow-up answer for {label_en}.",
            reused.next_step,
            f"{label_te} కోసం ఫాలో-అప్ సమాధానం కోసం ఎదురుచూస్తున్న ఆరోగ్య తనిఖీ ఏదీ లేదు.",
            reused.next_step_te,
        )


def _join(*parts: Text) -> Text:
    return Text(" ".join(p.en for p in parts), " ".join(p.te for p in parts))


# -- output ----------------------------------------------------------------------------------------------------------
class FollowUpOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    status: Literal["needs_confirmation", "changed", "cancelled"]
    check_id: str
    house_id: str
    number: int
    label_en: str
    label_te: str
    outcome: OutcomeName  # what the farmer said in this call
    # What is (or, on a read-back, would be) recorded: the most severe answer given, or "worse" when the record book
    # shows a death spike since the check. None when this call saved nothing and proposed nothing.
    recorded_as: OutcomeName | None
    # The follow-up's state now: after the save when status is "changed", unchanged otherwise.
    state: Literal["none", "scheduled", "due", "closed", "escalated", "superseded", "lapsed"]
    urgency: Literal["routine", "watch", "urgent", "notifiable_suspect"]  # the health check's own; never changed here
    escalated: bool  # the follow-up is (or, on a read-back, would be once saved) escalated
    reasons: list[str]  # codes (said_worse, record_book_spike, ...); never spoken
    record_book_worse: bool  # a death spike since the check: recorded as not better whatever the farmer says
    spike_deaths: int | None
    handoff_offered: bool  # prepare_vet_handoff is offered as a separate step; this tool sends nothing
    proposal_id: str | None
    expires_at: str | None
    expires_in_minutes: int | None
    reason: str | None
    replayed: bool


# -- finding the check this answer belongs to ------------------------------------------------------
def _confirmed_replay(
    source: DemoFarmSource, farm_id: str, outcome: str, proposal_id: str | None, checks: tuple[HealthCheck, ...]
) -> HealthCheck | None:
    """A repeated "yes" for a proposal already confirmed must be answered as a replay whatever state the follow-up is
    in now (idempotency, docs/DESIGN.md §5.1): the check it was confirmed for, or None."""
    if proposal_id is None:
        return None
    proposal = source.store.get_proposal(proposal_id)
    if (
        proposal is None
        or proposal.farm_id != farm_id
        or proposal.tool != TOOL
        or proposal.status is not ProposalStatus.CONFIRMED
        or proposal.arguments.get("outcome") != outcome
    ):
        return None
    return next((c for c in checks if c.check_id == proposal.arguments.get("check_id")), None)


def build_follow_up(
    source: DemoFarmSource,
    flow: ConfirmFlow,
    house_ref: str,
    outcome: str,
    check_id: str | None,
    proposal_id: str | None,
    answer: Answer | None,
) -> FollowUpOutput:
    farm, today = source.snapshot()
    house = resolve_house(farm, house_ref)
    store = source.store
    said = Outcome(outcome)
    label = Text(house.label_en, house.label_te)
    checks = tuple(
        _effective(c, source.now()) for c in store.recent_health_checks(farm.farm_id, house.house_id, date.min)
    )
    handed = _handoff_times(source, checks)

    def state_of(check: HealthCheck) -> FollowUp:
        answers = store.follow_up_answers(farm.farm_id, check.check_id)
        return follow_up_state(check, answers, handed, house, today, checks)

    check = _confirmed_replay(source, farm.farm_id, outcome, proposal_id, checks)
    if check is None:
        check = _pick(checks, check_id, state_of, house, said, today)

    args: dict[str, Any] = {"check_id": check.check_id, "outcome": outcome}

    def apply(proposal: Proposal, now: datetime) -> dict[str, Any]:
        # The record book's own verdict at the moment of saving (the domain's spike rule), never the farmer's words.
        fresh_farm, fresh_today = source.snapshot()
        fresh_house = resolve_house(fresh_farm, house.house_id)
        before = follow_up_state(
            check, store.follow_up_answers(farm.farm_id, check.check_id), handed, fresh_house, fresh_today, checks
        )
        saved = FollowUpAnswer(
            new_answer_id(),
            farm.farm_id,
            house.house_id,
            check.check_id,
            said,
            before.spike_day is not None,
            proposal.proposal_id,
            now,
        )
        store.add_follow_up_answer(saved)
        return {"answer_id": saved.answer_id}

    result = flow.run(farm.farm_id, TOOL, args, proposal_id, answer, apply)

    now_state = state_of(check)
    shown = now_state
    if result.status == "needs_confirmation":
        # The state if the farmer says yes: the domain decides, from a stand-in answer that is never saved.
        stand_in = FollowUpAnswer(
            new_answer_id(), farm.farm_id, house.house_id, check.check_id, said, False, "prop_" + "0" * 16, source.now()
        )
        shown = follow_up_state(
            check, (*store.follow_up_answers(farm.farm_id, check.check_id), stand_in), handed, house, today, checks
        )
    escalated = shown.state is FollowUpState.ESCALATED
    # Not better: "worse", "same" or "not sure", or a "better" that is recorded as not better (a death spike or an
    # earlier answer: the state is then escalated). It always ends with the vet line, whatever the follow-up's state
    # now: a handoff, or a newer check, may have taken the follow-up over, but the farmer still hears it.
    not_better = escalated or said is not Outcome.BETTER
    # The vet already has this check's summary (one handoff per check): speak the escalation, but offer no second one.
    offer = escalated and not shown.handed_off
    spike_deaths = _spike_deaths(house, shown.spike_day)
    fields: dict[str, Any] = {
        "demo_data": source.demo_data,
        "check_id": check.check_id,
        "house_id": house.house_id,
        "number": house.number,
        "label_en": house.label_en,
        "label_te": house.label_te,
        "outcome": outcome,
        "recorded_as": None if result.status == "cancelled" else (shown.outcome.value if shown.outcome else None),
        "state": now_state.state.value,
        "urgency": now_state.urgency.code,
        "escalated": escalated,
        "reasons": [r.value for r in shown.reasons],
        "record_book_worse": shown.spike_day is not None,
        "spike_deaths": spike_deaths,
        "handoff_offered": offer and result.status != "cancelled",
        "proposal_id": None,
        "expires_at": None,
        "expires_in_minutes": None,
        "reason": result.reason,
        "replayed": False,
    }
    if result.status == "needs_confirmation":
        p = result.proposal
        assert p is not None
        parts = [REASON_TEXT[result.reason]] if result.reason else []
        if spike_deaths is not None:
            parts.append(_spike_note(str(spike_deaths)))
        if not_better:
            parts.append(TO_BE_SAFE)
        parts.append(_ask(said, label))
        text = _join(*parts)
        fields.update(
            proposal_id=p.proposal_id,
            expires_at=p.expires_at.isoformat(),
            expires_in_minutes=int(PROPOSAL_TTL.total_seconds() // 60),
        )
        return FollowUpOutput(text_en=text.en, text_te=text.te, status="needs_confirmation", **fields)
    if result.status == "applied":
        fields["replayed"] = result.replayed
        text = _join(DONE, TO_BE_SAFE, OFFER) if offer else (_join(DONE, TO_BE_SAFE) if not_better else DONE)
        return FollowUpOutput(text_en=text.en, text_te=text.te, status="changed", **fields)
    fields["handoff_offered"] = False
    if result.reason == "already_done":
        text = REASON_TEXT["already_done"]
    else:
        text = _join(REASON_TEXT[result.reason], KEPT) if result.reason else KEPT
    return FollowUpOutput(text_en=text.en, text_te=text.te, status="cancelled", **fields)


def _spike_deaths(house: House, spike_day: date | None) -> int | None:
    if spike_day is None:
        return None
    return next((r.deaths for r in house.records if r.day == spike_day), None)


def _pick(
    checks: tuple[HealthCheck, ...],
    check_id: str | None,
    state_of: Callable[[HealthCheck], FollowUp],
    house: House,
    said: Outcome,
    today: date,
) -> HealthCheck:
    """The check this answer is for: the one named, else the newest on the shed that has a follow-up to answer."""
    if not checks:
        raise NoHealthCheck(house.label_en, house.label_te)
    if check_id is not None:
        found = next((c for c in checks if c.check_id == check_id), None)
        if found is None:
            raise NoHealthCheck(house.label_en, house.label_te)
        candidates = [found]
    else:
        candidates = list(checks)  # newest first
    for candidate in candidates:
        if _can_answer(state_of(candidate), candidate, said, today):
            return candidate
    raise NothingToFollowUp(house.label_en, house.label_te)


def _can_answer(fup: FollowUp, check: HealthCheck, said: Outcome, today: date) -> bool:
    """Is this check's follow-up waiting for an answer today?

    No for a check still being analyzed, one a newer check took over (it has its own follow-up), the day of the check
    itself (nothing to compare with yet), and a second "better" on a closed follow-up (nothing to add). A check that
    got a vet handoff still hears the farmer: its follow-up shows as handled, but "worse", "same" or "not sure" after
    the handoff escalates again, and "better" only closes it. A closed follow-up still hears a "worse" (a relapse)."""
    if fup.state is FollowUpState.NONE or not answerable(check, today):
        return False
    if fup.state is FollowUpState.SUPERSEDED and not fup.handed_off:
        return False
    return not (fup.state is FollowUpState.CLOSED and said is Outcome.BETTER)


def _handoff_times(source: DemoFarmSource, checks: tuple[HealthCheck, ...]) -> dict[str, datetime]:
    """When each check's vet handoff was sent (only checks that have one): the domain needs the time to tell what was
    said before the handoff from what is said after it."""
    found = {c.check_id: source.store.handoff_for_check(c.check_id) for c in checks}
    return {check_id: h.created_at for check_id, h in found.items() if h is not None}


# -- where a follow-up shows up: the briefing and the farm status share these sentences ------------
def _due_sentence(label: Text, days: int) -> Text:
    d, unit = num(days), plural(days, "day", "days")
    return Text(
        f"{label.en}: your health check {d} {unit} ago needs a follow-up. "
        "How are the birds now: better, the same, or worse?",
        f"{label.te}: {d} రోజుల క్రితం చేసిన మీ ఆరోగ్య తనిఖీకి ఫాలో-అప్ అవసరం. కోళ్లు ఇప్పుడు ఎలా ఉన్నాయి: మెరుగ్గా, అలాగే, లేదా అధ్వాన్నంగా?",
    )


def _escalated_sentence(label: Text, days: int) -> Text:
    d, unit = num(days), plural(days, "day", "days")
    first = Text(
        f"{label.en}: the follow-up on the health check {d} {unit} ago still needs attention.",
        f"{label.te}: {d} రోజుల క్రితం చేసిన ఆరోగ్య తనిఖీ ఫాలో-అప్‌పై ఇంకా శ్రద్ధ అవసరం.",
    )
    return _join(first, TO_BE_SAFE)


def _lapsed_sentence(label: Text, days: int) -> Text:
    d, unit = num(days), plural(days, "day", "days")
    return Text(
        f"{label.en}: there was no answer to the follow-up on the health check {d} {unit} ago.",
        f"{label.te}: {d} రోజుల క్రితం చేసిన ఆరోగ్య తనిఖీ ఫాలో-అప్‌కు సమాధానం రాలేదు.",
    )


def when_ago(days_ago: int) -> Text:
    """How the briefing and the status say how long ago a check was made (from the date passed in, never typed)."""
    if days_ago <= 0:
        return Text("earlier today", "ఈరోజు ముందు")
    if days_ago == 1:
        return Text("yesterday", "నిన్న")
    return Text(f"{days_ago} {plural(days_ago, 'day', 'days')} ago", f"{days_ago} రోజుల క్రితం")


def check_said_text(label: Text, urgency: Urgency, days_ago: int, ready: bool = True) -> Text:
    """What the health check told the farmer ("needs a vet today", "signs of a possible reportable disease"), in the
    reviewed sentence the briefing has always used. A follow-up on an urgent or reportable check keeps it (review
    finding B1): the question is added to the warning, never substituted for it."""
    when, short = when_ago(days_ago), URGENCY_SHORT[urgency]
    if ready:
        body = Text(f"your health check {when.en} said: {short.en}.", f"{when.te} మీ ఆరోగ్య తనిఖీ ఫలితం: {short.te}.")
    else:  # still running or failed: the level is the code floor from the signs, as in the health tool
        body = Text(
            f"your health check {when.en} is not finished; from the signs so far: {short.en}.",
            f"{when.te} మీ ఆరోగ్య తనిఖీ ఇంకా పూర్తి కాలేదు; ఇప్పటివరకు లక్షణాల ప్రకారం: {short.te}.",
        )
    return Text(f"{label.en}: {body.en}", f"{label.te}: {body.te}")


def warns_vet(urgency: Urgency) -> bool:
    """An urgent check or a suspected reportable disease: the warning and the vet closing line must not go away."""
    return urgency >= Urgency.URGENT


def follow_up_text(state: FollowUpState, urgency: Urgency, label: Text, days: int) -> Text:
    """The one sentence for a due or escalated follow-up. For an urgent or reportable check it starts with the
    check's own warning, so one item carries both; for a watch check it is the short question or escalation."""
    base = _escalated_sentence(label, days) if state is FollowUpState.ESCALATED else _due_sentence(label, days)
    return _join(check_said_text(label, urgency, days), base) if warns_vet(urgency) else base


def follow_up_days_ago(fup: FollowUp, as_of: date) -> int:
    """Days since the check, from the date passed in (never typed, never below zero)."""
    return 0 if fup.check_day is None else max(0, (as_of - fup.check_day).days)


def follow_up_line(fup: FollowUp, label: Text, as_of: date) -> Text | None:
    """The one spoken sentence for a shed's follow-up: a question when it is due, the escalation (with "To be safe,
    contact your vet or doctor"), or an honest "no answer" once it lapsed. Nothing for the other states."""
    days = follow_up_days_ago(fup, as_of)
    if fup.state in (FollowUpState.DUE, FollowUpState.ESCALATED):
        return follow_up_text(fup.state, fup.urgency, label, days)
    if fup.state is FollowUpState.LAPSED:
        return _lapsed_sentence(label, days)
    return None


# What the farmer should hear about first when a shed has several follow-ups (newest check first among equals).
_SURFACE_ORDER = (
    FollowUpState.ESCALATED,
    FollowUpState.DUE,
    FollowUpState.LAPSED,
    FollowUpState.SCHEDULED,
    FollowUpState.CLOSED,
)


def surfaced_follow_up(source: DemoFarmSource, farm_id: str, house: House, today: date) -> FollowUp | None:
    """The follow-up of this shed worth showing today, or None: an escalated one first (the most urgent check, then the
    newest), then a due one, a lapsed one, one not yet due, and a closed one. Nothing is slow: it reads this shed's
    stored checks and answers and works the states out in code."""
    store = source.store
    checks = tuple(_effective(c, source.now()) for c in store.recent_health_checks(farm_id, house.house_id, date.min))
    handed = _handoff_times(source, checks)
    best: tuple[tuple[int, int], FollowUp] | None = None
    for check in checks:  # newest first: on a tie the newest check stays
        fup = follow_up_state(check, store.follow_up_answers(farm_id, check.check_id), handed, house, today, checks)
        if fup.state not in _SURFACE_ORDER:
            continue
        key = (_SURFACE_ORDER.index(fup.state), -int(fup.urgency))
        if best is None or key < best[0]:
            best = (key, fup)
    return None if best is None else best[1]


@dataclass(frozen=True)
class ShedHealth:
    """Everything stored about one shed's health that the briefing and the farm status read, gathered in one place so
    both work from the same inputs (review finding H1)."""

    check: HealthCheck | None  # the shed's latest check
    recent: tuple[HealthCheck, ...]  # its checks from the last NOTIFIABLE_DAYS days
    handed_off: frozenset[str]  # ids of suspected-reportable checks whose vet handoff was confirmed
    follow_up: FollowUp | None  # the follow-up worth showing today, in any state
    fact: Fact | None  # its one health item (open check or follow-up), the same one the briefing lists


def shed_health(source: DemoFarmSource, farm_id: str, house: House, as_of: date) -> ShedHealth:
    """Stored checks, answers and handoffs for one shed and the day: no model, nothing slow."""
    store = source.store
    fup = surfaced_follow_up(source, farm_id, house, as_of)
    check = store.latest_health_check(farm_id, house.house_id)
    recent = store.recent_health_checks(farm_id, house.house_id, as_of - timedelta(days=NOTIFIABLE_DAYS))
    handed = frozenset(  # only a confirmed vet handoff (written after "yes") ends a suspected reportable disease item
        c.check_id
        for c in recent
        if check_urgency(c) is Urgency.NOTIFIABLE_SUSPECT and store.handoff_for_check(c.check_id) is not None
    )
    return ShedHealth(check, recent, handed, fup, health_fact(house, as_of, check, recent, handed, fup))


class FollowUpView(BaseModel):
    """A shed's follow-up as farm status reports it (the card will show exactly this; docs/DESIGN.md §14)."""

    model_config = ConfigDict(extra="forbid")
    check_id: str
    state: Literal["scheduled", "due", "closed", "escalated", "lapsed"]
    urgency: Literal["watch", "urgent", "notifiable_suspect"]  # the health check's own; never changed by an answer
    days_ago: int
    due_day: str
    outcome: OutcomeName | None
    reasons: list[str]  # codes; never spoken
    handed_off: bool
    text_en: str | None  # the sentence spoken for it (due, escalated, lapsed); None for the others
    text_te: str | None


def follow_up_view(fup: FollowUp, label: Text, as_of: date) -> FollowUpView:
    line = follow_up_line(fup, label, as_of)
    assert fup.due_day is not None
    return FollowUpView(
        check_id=fup.check_id,
        state=fup.state.value,  # type: ignore[arg-type]
        urgency=fup.urgency.code,  # type: ignore[arg-type]
        days_ago=follow_up_days_ago(fup, as_of),
        due_day=fup.due_day.isoformat(),
        outcome=None if fup.outcome is None else fup.outcome.value,
        reasons=[r.value for r in fup.reasons],
        handed_off=fup.handed_off,
        text_en=None if line is None else line.en,
        text_te=None if line is None else line.te,
    )


# -- registration ----------------------------------------------------------------------------------
DESCRIPTION = (
    "Use when the farmer says how a shed that had a health check is doing now compared with then: better (theek, "
    "behtar), the same (waisa hi, no change), worse (aur kharab), or not sure (pata nahi). Give the house (shed, "
    "house, kotam) and `outcome`: one of better, same, worse, not_sure. If the farmer describes new signs of illness "
    "(coughing, swollen head, sudden deaths) call start_health_check instead. Always two calls: first only the house "
    "and the outcome; nothing is saved and the result reads it back. Then call again with the same arguments plus "
    "the returned `proposal_id` and `answer`: 'yes' for an explicit spoken yes (haan, avunu), 'no' for no (nahi, "
    "vaddu). The answer never lowers a health check's urgency; a death spike in the record book since the check "
    "counts as worse. There is no free-text argument and no medicine or dose is ever involved."
)


def register(server: MCPServer, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    flow = ConfirmFlow(source.store, source.now)

    @server.tool(
        name=TOOL,
        title="Tell how a shed is now",
        description=DESCRIPTION,
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
    )
    def report_health_follow_up(
        house: Annotated[str, HOUSE_PARAM],
        outcome: OutcomeName,
        check_id: Annotated[CheckId | None, CHECK_PARAM] = None,
        proposal_id: Annotated[ProposalId | None, PROPOSAL_PARAM] = None,
        answer: Annotated[Answer | None, ANSWER_PARAM] = None,
    ) -> Annotated[CallToolResult, FollowUpOutput]:
        try:
            out = build_follow_up(source, flow, house, outcome, check_id, proposal_id, answer)
        except DomainError as err:
            return domain_error_result(err)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name=TOOL,
            title=Text("Tell how a shed is now", "షెడ్ ఇప్పుడు ఎలా ఉందో చెప్పండి"),
            example_en="Shed 2 is better now",
        )
    )
