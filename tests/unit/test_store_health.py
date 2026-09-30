"""Health checks, vet handoffs and the AI call ledger in SqliteStore (docs/DESIGN.md §18)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from clucktalk.domain.triage import (
    Category,
    CheckStatus,
    Confidence,
    HealthCheck,
    Sign,
    TriageInput,
    TriageResult,
    Urgency,
    VetHandoff,
    floor_urgency,
    new_check_id,
    new_handoff_id,
)
from clucktalk.store.sqlite import SqliteStore

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 9, 29, 10, 0, tzinfo=IST)
INP = TriageInput("house-2", "House 2", "షెడ్ 2", "Ross 308", 23, 3870, (Sign.COUGHING,), "coughing", None, None,
                  26, 4.0, True, None, "2026-09-29")  # fmt: skip


def _check(house="house-2", at=T0) -> HealthCheck:
    floor = floor_urgency(frozenset(INP.signs), True)
    return HealthCheck(new_check_id(), "farm", house, at, CheckStatus.ANALYZING, INP, floor, None, at)


def test_health_check_round_trip_update_and_latest():
    s = SqliteStore()
    a, b = _check(at=T0), _check(at=T0 + timedelta(minutes=1))
    s.add_health_check(a)
    s.add_health_check(b)
    s.add_health_check(_check(house="house-1", at=T0 + timedelta(minutes=2)))
    assert s.get_health_check(a.check_id) == a
    assert s.latest_health_check("farm", "house-2") == b
    result = TriageResult(Urgency.URGENT, ((Category.RESPIRATORY, Confidence.MEDIUM),), ("call_vet_today",),
                          "rules", None, None)  # fmt: skip
    done = replace(b, status=CheckStatus.READY, result=result, updated_at=T0 + timedelta(minutes=3))
    s.update_health_check(done)
    assert s.get_health_check(b.check_id) == done
    assert s.get_health_check("chk_0000000000000000") is None
    assert s.latest_health_check("farm", "house-9") is None


def test_handoff_round_trip():
    s = SqliteStore()
    c = _check()
    s.add_health_check(c)
    assert s.handoff_for_check(c.check_id) is None
    h = VetHandoff(new_handoff_id(), "farm", c.check_id, T0, "summary", "సారాంశం")
    s.add_handoff(h)
    assert s.handoff_for_check(c.check_id) == h


def test_ai_call_ledger_by_day():
    s = SqliteStore()
    s.add_ai_call(T0, "triage", "nova", "m", 10, 2, 300, "ok")
    s.add_ai_call(T0 + timedelta(days=1), "triage", "nova", "m", 11, 3, 310, "ok")
    assert [c["input_tokens"] for c in s.ai_calls(T0.date())] == [10]
    assert s.count_ai_calls(T0.date()) == 1 and s.count_ai_calls(T0.date(), agent="briefing") == 0


def test_briefing_rank_round_trip_is_per_farm_day_and_replaces():
    from datetime import date

    from clucktalk.domain.briefing import BriefingRank

    store = SqliteStore()
    d = date(2026, 9, 29)
    assert store.get_briefing_rank("farm-x", d) is None
    store.save_briefing_rank(BriefingRank("farm-x", d, "fp1", ("a", "b"), "nova", "model-1", None))
    assert store.get_briefing_rank("farm-x", d) == BriefingRank("farm-x", d, "fp1", ("a", "b"), "nova", "model-1", None)
    store.save_briefing_rank(BriefingRank("farm-x", d, "fp2", (), "rules", None, "daily_limit"))
    got = store.get_briefing_rank("farm-x", d)
    assert (got.fingerprint, got.order, got.note) == ("fp2", (), "daily_limit")
    assert store.get_briefing_rank("farm-x", date(2026, 9, 30)) is None and store.get_briefing_rank("farm-y", d) is None
