"""The one confirmation pattern (docs/DESIGN.md §5.1), as pure rules with no I/O.

A change is first proposed (nothing changes; the farmer hears a read-back), then the host calls the same tool again
with the ``proposal_id`` and the farmer's answer. ``decide`` says what that second call may do; the server's
confirmation flow (clucktalk.server.confirm) carries it out against the state store.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import StringConstraints

PROPOSAL_TTL = timedelta(minutes=10)
PROPOSAL_ID_PATTERN = r"^prop_[0-9a-f]{16}$"
# Shared tool-parameter type: every confirmation-pattern tool (docs/DESIGN.md §5.1) takes proposal_id like this.
ProposalId = Annotated[str, StringConstraints(pattern=PROPOSAL_ID_PATTERN)]

Answer = Literal["yes", "no"]
# Why a second call could not apply the proposal it names (spoken, so the farmer knows nothing changed).
Reason = Literal["expired", "superseded", "changed", "unknown", "cancelled_earlier", "already_done"]


class ProposalStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


def new_proposal_id() -> str:
    return "prop_" + secrets.token_hex(8)


def canonical(arguments: dict[str, Any]) -> str:
    """Arguments as canonical JSON, so "same arguments as the read-back" is an exact comparison."""
    return json.dumps(arguments, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    farm_id: str
    tool: str
    arguments: dict[str, Any]  # the change, exactly as read back
    created_at: datetime
    expires_at: datetime
    status: ProposalStatus = ProposalStatus.PENDING
    resolved_at: datetime | None = None
    outcome: dict[str, Any] | None = None  # what was applied; replayed for a repeated "yes" (idempotency)

    def __post_init__(self) -> None:
        if self.expires_at <= self.created_at:
            raise ValueError(f"{self.proposal_id}: expires_at must be after created_at")
        if (self.status is ProposalStatus.PENDING) != (self.resolved_at is None):
            raise ValueError(f"{self.proposal_id}: only a pending proposal has no resolved_at")
        if (self.status is ProposalStatus.CONFIRMED) != (self.outcome is not None):
            raise ValueError(f"{self.proposal_id}: exactly the confirmed proposals carry an outcome")

    def resolved(self, status: ProposalStatus, at: datetime, outcome: dict[str, Any] | None = None) -> Proposal:
        return replace(self, status=status, resolved_at=at, outcome=outcome)


def new_proposal(farm_id: str, tool: str, arguments: dict[str, Any], now: datetime) -> Proposal:
    return Proposal(new_proposal_id(), farm_id, tool, dict(arguments), now, now + PROPOSAL_TTL)


class Decision(StrEnum):
    APPLY = "apply"  # pending, unexpired, same arguments, answer yes: make the change once
    CANCEL = "cancel"  # pending, answer no: nothing changes
    REPLAY = "replay"  # already confirmed with these arguments: return the stored outcome, change nothing
    PROPOSE = "propose"  # cannot apply: nothing changes, read the (new) request back again
    NOTHING = "nothing"  # answer no to something no longer pending: nothing changes, nothing to ask


def decide(
    proposal: Proposal | None, *, farm_id: str, tool: str, arguments: dict[str, Any], answer: Answer, now: datetime
) -> tuple[Decision, Reason | None]:
    """What a second call (``proposal_id`` + answer) may do. Only an exact, live match can change anything, and a
    "no" never leads to a new read-back (the farmer just declined)."""
    if proposal is None or proposal.farm_id != farm_id or proposal.tool != tool:
        return (Decision.NOTHING if answer == "no" else Decision.PROPOSE), "unknown"
    same = canonical(proposal.arguments) == canonical(arguments)
    if proposal.status is ProposalStatus.CONFIRMED:
        if answer == "no":  # too late to decline: it was applied earlier; say so, never "Done"
            return Decision.NOTHING, ("already_done" if same else None)
        return (Decision.REPLAY, None) if same else (Decision.PROPOSE, "changed")
    if proposal.status is ProposalStatus.CANCELLED:
        return (Decision.NOTHING, None) if answer == "no" else (Decision.PROPOSE, "cancelled_earlier")
    if proposal.status is ProposalStatus.SUPERSEDED:
        stale: Reason | None = "superseded"
    elif proposal.status is ProposalStatus.EXPIRED or now >= proposal.expires_at:
        stale = "expired"
    else:
        stale = None
    if stale is not None:
        return (Decision.NOTHING if answer == "no" else Decision.PROPOSE), stale
    if answer == "no":
        return Decision.CANCEL, None
    return (Decision.APPLY, None) if same else (Decision.PROPOSE, "changed")
