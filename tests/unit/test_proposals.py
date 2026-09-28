"""The confirmation rules (docs/DESIGN.md §5.1), as a table: expected decisions come from the rules, not the code."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from clucktalk.domain.proposals import (
    PROPOSAL_ID_PATTERN,
    PROPOSAL_TTL,
    Decision,
    Proposal,
    ProposalStatus,
    canonical,
    decide,
    new_proposal,
)

T0 = datetime(2026, 9, 29, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
ARGS = {"mode": "contract"}


def _p(status=ProposalStatus.PENDING, farm="farm-1", tool="set_farm_mode", args=None) -> Proposal:
    p = new_proposal(farm, tool, args or ARGS, T0)
    if status is ProposalStatus.CONFIRMED:
        return p.resolved(status, T0 + timedelta(minutes=1), {"mode": "contract"})
    return p if status is ProposalStatus.PENDING else p.resolved(status, T0 + timedelta(minutes=1))


def _decide(p, answer="yes", now=T0 + timedelta(minutes=2), args=None, farm="farm-1", tool="set_farm_mode"):
    return decide(p, farm_id=farm, tool=tool, arguments=args or ARGS, answer=answer, now=now)


@pytest.mark.parametrize(
    ("case", "proposal", "kwargs", "expected"),
    [
        ("live match, yes", _p(), {}, (Decision.APPLY, None)),
        ("live match, no", _p(), {"answer": "no"}, (Decision.CANCEL, None)),
        ("live, other arguments, yes", _p(), {"args": {"mode": "independent"}}, (Decision.PROPOSE, "changed")),
        ("live, other arguments, no", _p(), {"answer": "no", "args": {"mode": "independent"}}, (Decision.CANCEL, None)),
        ("expired by time, yes", _p(), {"now": T0 + PROPOSAL_TTL}, (Decision.PROPOSE, "expired")),
        ("expired by time, no", _p(), {"answer": "no", "now": T0 + PROPOSAL_TTL}, (Decision.NOTHING, "expired")),
        ("marked expired, yes", _p(ProposalStatus.EXPIRED), {}, (Decision.PROPOSE, "expired")),
        ("superseded, yes", _p(ProposalStatus.SUPERSEDED), {}, (Decision.PROPOSE, "superseded")),
        ("superseded, no", _p(ProposalStatus.SUPERSEDED), {"answer": "no"}, (Decision.NOTHING, "superseded")),
        ("cancelled, yes", _p(ProposalStatus.CANCELLED), {}, (Decision.PROPOSE, "cancelled_earlier")),
        ("cancelled, no again", _p(ProposalStatus.CANCELLED), {"answer": "no"}, (Decision.NOTHING, None)),
        ("confirmed, same yes again", _p(ProposalStatus.CONFIRMED), {}, (Decision.REPLAY, None)),
        # Review 2026-09-28: a "no" after the change was applied must not be answered with "Done".
        ("confirmed, then no", _p(ProposalStatus.CONFIRMED), {"answer": "no"}, (Decision.NOTHING, "already_done")),
        # Review: a "no" never produces a new read-back.
        (
            "confirmed, no with other arguments",
            _p(ProposalStatus.CONFIRMED),
            {"answer": "no", "args": {"mode": "independent"}},
            (Decision.NOTHING, None),
        ),
        (
            "confirmed, other arguments",
            _p(ProposalStatus.CONFIRMED),
            {"args": {"mode": "independent"}},
            (Decision.PROPOSE, "changed"),
        ),
        ("unknown id, yes", None, {}, (Decision.PROPOSE, "unknown")),
        ("unknown id, no", None, {"answer": "no"}, (Decision.NOTHING, "unknown")),
        ("another farm's proposal", _p(farm="farm-2"), {}, (Decision.PROPOSE, "unknown")),
        ("another tool's proposal", _p(tool="log_daily_record"), {}, (Decision.PROPOSE, "unknown")),
    ],
)
def test_decide(case, proposal, kwargs, expected):
    assert _decide(proposal, **kwargs) == expected, case


@pytest.mark.parametrize("status", list(ProposalStatus) + [None])
@pytest.mark.parametrize("args", [ARGS, {"mode": "independent"}])
def test_no_never_leads_to_a_new_read_back_or_a_change(status, args):
    p = None if status is None else _p(status)
    decision, _ = _decide(p, answer="no", args=args)
    assert decision in (Decision.CANCEL, Decision.NOTHING)


def test_a_proposal_is_live_until_exactly_its_expiry():
    p = _p()
    assert _decide(p, now=p.expires_at - timedelta(seconds=1)) == (Decision.APPLY, None)
    assert _decide(p, now=p.expires_at) == (Decision.PROPOSE, "expired")


def test_new_proposal_shape():
    p = new_proposal("farm-1", "set_farm_mode", ARGS, T0)
    assert re.fullmatch(PROPOSAL_ID_PATTERN, p.proposal_id)
    assert p.status is ProposalStatus.PENDING and p.resolved_at is None and p.outcome is None
    assert p.expires_at - p.created_at == PROPOSAL_TTL == timedelta(minutes=10)
    assert new_proposal("farm-1", "set_farm_mode", ARGS, T0).proposal_id != p.proposal_id


def test_arguments_compare_exactly_regardless_of_key_order():
    assert canonical({"b": 1, "a": "x"}) == canonical({"a": "x", "b": 1})
    assert canonical({"a": 1}) != canonical({"a": 1.5})


@pytest.mark.parametrize(
    "bad",
    [
        {"status": ProposalStatus.CONFIRMED, "resolved_at": T0, "outcome": None},  # confirmed needs an outcome
        {"status": ProposalStatus.PENDING, "resolved_at": T0, "outcome": None},  # pending is unresolved
        {"status": ProposalStatus.CANCELLED, "resolved_at": None, "outcome": None},  # resolved needs a time
        {"status": ProposalStatus.CANCELLED, "resolved_at": T0, "outcome": {"mode": "contract"}},
    ],
)
def test_inconsistent_proposals_are_rejected(bad):
    with pytest.raises(ValueError):
        Proposal("prop_0123456789abcdef", "farm-1", "t", ARGS, T0, T0 + PROPOSAL_TTL, **bad)
