"""The one confirmation pattern (docs/DESIGN.md §5.1), carried out against the state store.

Every tool that changes something calls ``ConfirmFlow.run`` with its own name and the change's arguments:
- no ``proposal_id``: a new proposal is stored and returned for the read-back; nothing changes;
- ``proposal_id`` + answer: ``clucktalk.domain.proposals.decide`` rules, applied inside one store transaction, so
  the change happens at most once however often the same "yes" arrives.
The tool renders the result into speech; this module never speaks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from clucktalk.domain.errors import AnswerWithoutProposal, MissingAnswer
from clucktalk.domain.proposals import Answer, Decision, Proposal, ProposalStatus, Reason, decide, new_proposal
from clucktalk.store import Store

Status = Literal["needs_confirmation", "applied", "cancelled", "already_set"]
# Applies the confirmed change inside the store transaction; returns the outcome to keep (and replay).
Apply = Callable[[Proposal, datetime], dict[str, Any]]


@dataclass(frozen=True)
class ConfirmResult:
    status: Status
    proposal: Proposal | None  # the proposal to read back (needs_confirmation) or the one resolved
    reason: Reason | None = None  # why an answer could not be applied as given
    replayed: bool = False  # "applied" earlier; this call changed nothing


class ConfirmFlow:
    def __init__(self, store: Store, now: Callable[[], datetime]) -> None:
        self.store = store
        self.now = now

    def run(
        self,
        farm_id: str,
        tool: str,
        arguments: dict[str, Any],
        proposal_id: str | None,
        answer: Answer | None,
        apply: Apply,
        *,
        in_place: Callable[[], bool] = lambda: False,
    ) -> ConfirmResult:
        """``in_place`` says whether the requested state already holds; it is read inside the transaction. Then a
        new request proposes nothing (``already_set``) and withdraws any older pending read-back, since the
        farmer's latest request replaces it; an answer that cannot be applied changes nothing and asks nothing."""
        if proposal_id is None and answer is not None:
            raise AnswerWithoutProposal()
        if proposal_id is not None and answer is None:
            raise MissingAnswer()
        with self.store.atomic():
            now = self.now()
            if proposal_id is None:
                if in_place():
                    self._withdraw_pending(farm_id, tool, now)
                    return ConfirmResult("already_set", None)
                return ConfirmResult("needs_confirmation", self._propose(farm_id, tool, arguments, now))
            assert answer is not None  # checked above; narrows the type
            proposal = self.store.get_proposal(proposal_id)
            if proposal is not None and proposal.status is ProposalStatus.PENDING and now >= proposal.expires_at:
                proposal = proposal.resolved(ProposalStatus.EXPIRED, now)
                self.store.update_proposal(proposal)
            decision, reason = decide(proposal, farm_id=farm_id, tool=tool, arguments=arguments, answer=answer, now=now)
            if decision is Decision.APPLY:
                assert proposal is not None
                done = proposal.resolved(ProposalStatus.CONFIRMED, now, apply(proposal, now))
                self.store.update_proposal(done)
                return ConfirmResult("applied", done)
            if decision is Decision.REPLAY:
                return ConfirmResult("applied", proposal, replayed=True)
            if decision is Decision.CANCEL:
                assert proposal is not None
                cancelled = proposal.resolved(ProposalStatus.CANCELLED, now)
                self.store.update_proposal(cancelled)
                return ConfirmResult("cancelled", cancelled)
            if decision is Decision.NOTHING or in_place():  # no point reading back a change already in place
                return ConfirmResult("cancelled", proposal, reason)
            return ConfirmResult("needs_confirmation", self._propose(farm_id, tool, arguments, now), reason)

    def _withdraw_pending(self, farm_id: str, tool: str, now: datetime) -> None:
        """Older pending proposals for this farm and tool end (superseded, or expired if past their time)."""
        for old in self.store.pending_proposals(farm_id, tool):
            status = ProposalStatus.EXPIRED if now >= old.expires_at else ProposalStatus.SUPERSEDED
            self.store.update_proposal(old.resolved(status, now))

    def _propose(self, farm_id: str, tool: str, arguments: dict[str, Any], now: datetime) -> Proposal:
        """A new proposal; any older pending one for this farm and tool is superseded (§5.1 point 5)."""
        self._withdraw_pending(farm_id, tool, now)
        proposal = new_proposal(farm_id, tool, arguments, now)
        self.store.add_proposal(proposal)
        return proposal
