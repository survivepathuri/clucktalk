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
from datetime import date, datetime
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict

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
from clucktalk.domain.triage import HealthCheck
from clucktalk.i18n import Text
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.tools import Capability, CapabilityRegistry
from clucktalk.server.tools.health import (
    ANSWER_PARAM,
    CHECK_PARAM,
    HOUSE_PARAM,
    OFFER,
    PROPOSAL_PARAM,
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


# -- finding the check this answer belongs to --------------------------------------------------------------------------
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
    handed = frozenset(c.check_id for c in checks if store.handoff_for_check(c.check_id) is not None)

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
        "handoff_offered": escalated and result.status != "cancelled",
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
        if escalated:
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
        text = _join(DONE, TO_BE_SAFE, OFFER) if escalated else DONE
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
    if check_id is not None:
        found = next((c for c in checks if c.check_id == check_id), None)
        if found is None:
            raise NoHealthCheck(house.label_en, house.label_te)
        candidate, fup = found, state_of(found)
    else:
        if not checks:
            raise NoHealthCheck(house.label_en, house.label_te)
        for candidate in checks:  # newest first
            fup = state_of(candidate)
            if fup.state not in (FollowUpState.NONE, FollowUpState.SUPERSEDED):
                break
        else:
            raise NothingToFollowUp(house.label_en, house.label_te)
    unanswerable = fup.state in (FollowUpState.NONE, FollowUpState.SUPERSEDED) or not answerable(candidate, today)
    # A second "better" on a follow-up that is already closed has nothing to add; "same", "worse" or "not sure" does
    # (it reopens it): the birds can get worse after they were better.
    if unanswerable or (fup.state is FollowUpState.CLOSED and said is Outcome.BETTER):
        raise NothingToFollowUp(house.label_en, house.label_te)
    return candidate


# -- registration -----------------------------------------------------------------------------------------------------
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
