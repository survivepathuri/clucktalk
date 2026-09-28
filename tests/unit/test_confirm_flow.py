"""ConfirmFlow against a real (in-memory) store: a change happens once, only after an explicit live "yes"
(docs/DESIGN.md §5.1). ``applied`` counts how often the change really ran."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from clucktalk.domain.errors import AnswerWithoutProposal, MissingAnswer
from clucktalk.domain.proposals import PROPOSAL_TTL, ProposalStatus
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.store.sqlite import SqliteStore

T0 = datetime(2026, 9, 29, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
TOOL = "set_farm_mode"
ARGS = {"mode": "contract"}


class Clock:
    def __init__(self) -> None:
        self.t = T0

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def env():
    store, clock, applied = SqliteStore(), Clock(), []

    def apply(proposal, now):
        applied.append((proposal.proposal_id, now))
        return dict(proposal.arguments)

    return ConfirmFlow(store, clock), store, clock, applied, apply


def test_propose_changes_nothing_then_yes_applies_once(env):
    flow, store, clock, applied, apply = env
    first = flow.run("farm-1", TOOL, ARGS, None, None, apply)
    assert first.status == "needs_confirmation" and applied == []
    pid = first.proposal.proposal_id
    clock.t += timedelta(minutes=3)
    yes = flow.run("farm-1", TOOL, ARGS, pid, "yes", apply)
    assert yes.status == "applied" and not yes.replayed and applied == [(pid, clock.t)]
    assert store.get_proposal(pid).status is ProposalStatus.CONFIRMED
    for _ in range(3):  # the same "yes" again (retry, duplicate host call)
        again = flow.run("farm-1", TOOL, ARGS, pid, "yes", apply)
        assert again.status == "applied" and again.replayed
    assert len(applied) == 1


def test_no_cancels_and_a_later_yes_cannot_revive_it(env):
    flow, store, _, applied, apply = env
    pid = flow.run("farm-1", TOOL, ARGS, None, None, apply).proposal.proposal_id
    assert flow.run("farm-1", TOOL, ARGS, pid, "no", apply).status == "cancelled"
    later = flow.run("farm-1", TOOL, ARGS, pid, "yes", apply)
    assert later.status == "needs_confirmation" and later.reason == "cancelled_earlier"
    assert later.proposal.proposal_id != pid and applied == []


def test_expired_yes_changes_nothing_and_reads_back_again(env):
    flow, store, clock, applied, apply = env
    pid = flow.run("farm-1", TOOL, ARGS, None, None, apply).proposal.proposal_id
    clock.t += PROPOSAL_TTL
    late = flow.run("farm-1", TOOL, ARGS, pid, "yes", apply)
    assert late.status == "needs_confirmation" and late.reason == "expired" and applied == []
    assert store.get_proposal(pid).status is ProposalStatus.EXPIRED


def test_a_newer_proposal_supersedes_the_older_one(env):
    flow, store, _, applied, apply = env
    old = flow.run("farm-1", TOOL, ARGS, None, None, apply).proposal.proposal_id
    new = flow.run("farm-1", TOOL, {"mode": "independent"}, None, None, apply).proposal.proposal_id
    assert store.get_proposal(old).status is ProposalStatus.SUPERSEDED
    assert [p.proposal_id for p in store.pending_proposals("farm-1", TOOL)] == [new]
    stale = flow.run("farm-1", TOOL, ARGS, old, "yes", apply)
    assert stale.status == "needs_confirmation" and stale.reason == "superseded" and applied == []


def test_yes_with_other_arguments_than_the_read_back_applies_nothing(env):
    flow, _, _, applied, apply = env
    pid = flow.run("farm-1", TOOL, ARGS, None, None, apply).proposal.proposal_id
    mixed = flow.run("farm-1", TOOL, {"mode": "independent"}, pid, "yes", apply)
    assert mixed.status == "needs_confirmation" and mixed.reason == "changed" and applied == []
    assert mixed.proposal.arguments == {"mode": "independent"}  # the new read-back is for what was asked now


def test_an_unusable_answer_for_a_state_already_in_place_just_changes_nothing(env):
    flow, store, _, applied, apply = env
    pid = flow.run("farm-1", TOOL, ARGS, None, None, apply).proposal.proposal_id
    out = flow.run("farm-1", TOOL, {"mode": "independent"}, pid, "yes", apply, in_place=lambda: True)
    assert out.status == "cancelled" and out.reason == "changed" and applied == []
    assert [p.proposal_id for p in store.pending_proposals("farm-1", TOOL)] == [pid]  # no new read-back made


def test_a_newer_request_for_the_state_in_place_withdraws_the_older_read_back(env):
    """Review 2026-09-28 (Medium): "switch to contract", then "switch to independent" (already so), then a late
    yes to the first read-back must not apply contract (§5.1 point 5: the latest request replaces the older)."""
    flow, store, _, applied, apply = env
    pid = flow.run("farm-1", TOOL, ARGS, None, None, apply).proposal.proposal_id
    same = flow.run("farm-1", TOOL, {"mode": "independent"}, None, None, apply, in_place=lambda: True)
    assert same.status == "already_set" and store.get_proposal(pid).status is ProposalStatus.SUPERSEDED
    late = flow.run("farm-1", TOOL, ARGS, pid, "yes", apply)
    assert late.status == "needs_confirmation" and late.reason == "superseded" and applied == []


def test_unknown_or_foreign_proposal_ids_apply_nothing(env):
    flow, _, _, applied, apply = env
    pid = flow.run("farm-2", TOOL, ARGS, None, None, apply).proposal.proposal_id
    assert flow.run("farm-1", TOOL, ARGS, pid, "yes", apply).reason == "unknown"
    assert flow.run("farm-1", TOOL, ARGS, "prop_0000000000000000", "yes", apply).reason == "unknown"
    assert applied == []


def test_answer_and_proposal_id_come_together(env):
    flow, _, _, applied, apply = env
    with pytest.raises(AnswerWithoutProposal):
        flow.run("farm-1", TOOL, ARGS, None, "yes", apply)
    with pytest.raises(MissingAnswer):
        flow.run("farm-1", TOOL, ARGS, "prop_0000000000000000", None, apply)
    assert applied == []


def test_a_failing_change_leaves_the_proposal_pending(env):
    flow, store, _, _, _ = env
    pid = flow.run("farm-1", TOOL, ARGS, None, None, lambda p, n: {}).proposal.proposal_id

    def broken(proposal, now):
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        flow.run("farm-1", TOOL, ARGS, pid, "yes", broken)
    assert store.get_proposal(pid).status is ProposalStatus.PENDING  # rolled back: the farmer can say yes again
