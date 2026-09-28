"""SqliteStore: round trips, persistence across restarts, transactions, and loud failures (Rule 6)."""

from __future__ import annotations

import sqlite3
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone

import pytest

from clucktalk.domain.models import DailyRecord, Treatment, TreatmentKind
from clucktalk.domain.profile import FarmMode, FarmProfile
from clucktalk.domain.proposals import ProposalStatus, new_proposal
from clucktalk.store import StoreError
from clucktalk.store.sqlite import SqliteStore

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 9, 29, 10, 0, tzinfo=IST)


def test_profile_round_trip_and_replace():
    s = SqliteStore()
    assert s.get_profile("farm-1") is None
    s.save_profile(FarmProfile("farm-1", FarmMode.CONTRACT, "farmer", T0))
    assert s.get_profile("farm-1") == FarmProfile("farm-1", FarmMode.CONTRACT, "farmer", T0)
    s.save_profile(FarmProfile("farm-1", FarmMode.INDEPENDENT, "farmer", T0 + timedelta(hours=1)))
    assert s.get_profile("farm-1").mode is FarmMode.INDEPENDENT
    assert s.get_profile("farm-2") is None


def test_proposal_round_trip_pending_query_and_update():
    s = SqliteStore()
    a = new_proposal("farm-1", "set_farm_mode", {"mode": "contract"}, T0)
    b = new_proposal("farm-1", "other_tool", {"x": 1}, T0)
    s.add_proposal(a)
    s.add_proposal(b)
    assert s.get_proposal(a.proposal_id) == a
    assert s.pending_proposals("farm-1", "set_farm_mode") == [a]
    done = a.resolved(ProposalStatus.CONFIRMED, T0 + timedelta(minutes=1), {"mode": "contract"})
    s.update_proposal(done)
    assert s.get_proposal(a.proposal_id) == done
    assert s.pending_proposals("farm-1", "set_farm_mode") == []
    with pytest.raises(StoreError):
        s.update_proposal(new_proposal("farm-1", "set_farm_mode", {}, T0))  # never stored


def test_records_round_trip_with_treatments_sorted_and_replaced_per_day():
    s = SqliteStore()
    r2 = DailyRecord(date(2026, 9, 29), 3, 410.5, avg_weight_g=980.0, weight_sample_birds=20)
    r1 = DailyRecord(
        date(2026, 9, 28),
        2,
        400.0,
        treatments=(
            Treatment(TreatmentKind.VACCINE, "Lasota", "in drinking water"),
            Treatment(TreatmentKind.MEDICINE, "vitamin tonic"),
        ),
    )
    s.put_record("farm-1", "house-2", r2)
    s.put_record("farm-1", "house-2", r1)
    assert s.records("farm-1", "house-2") == (r1, r2)
    corrected = DailyRecord(date(2026, 9, 29), 4, 410.5)
    s.put_record("farm-1", "house-2", corrected)
    assert s.records("farm-1", "house-2") == (r1, corrected)
    assert s.records("farm-1", "house-1") == ()


def test_state_survives_a_restart(tmp_path):
    path = tmp_path / "state" / "clucktalk.sqlite3"  # parent folder does not exist yet
    s = SqliteStore(path)
    s.save_profile(FarmProfile("farm-1", FarmMode.CONTRACT, "farmer", T0))
    s.close()
    again = SqliteStore(path)
    assert again.get_profile("farm-1").mode is FarmMode.CONTRACT
    again.close()


def test_atomic_rolls_back_everything_on_error():
    s = SqliteStore()
    with pytest.raises(RuntimeError), s.atomic():
        s.save_profile(FarmProfile("farm-1", FarmMode.CONTRACT, "farmer", T0))
        s.add_proposal(new_proposal("farm-1", "set_farm_mode", {"mode": "contract"}, T0))
        raise RuntimeError("boom")
    assert s.get_profile("farm-1") is None
    assert s.pending_proposals("farm-1", "set_farm_mode") == []


class _FailingCommit:
    """Wraps the connection; COMMIT fails once (e.g. 'database is locked' from another process)."""

    def __init__(self, db):
        self.db, self.failed = db, False

    def execute(self, sql, *args):
        if sql == "COMMIT" and not self.failed:
            self.failed = True
            raise sqlite3.OperationalError("database is locked")
        return self.db.execute(sql, *args)

    @property
    def in_transaction(self):
        return self.db.in_transaction


def test_a_failed_commit_rolls_back_and_the_store_stays_usable():
    """Review 2026-09-28 (Medium): a failed COMMIT left the connection inside the transaction."""
    s = SqliteStore()
    real = s._db
    s._db = _FailingCommit(real)
    with pytest.raises(sqlite3.OperationalError):
        s.save_profile(FarmProfile("farm-1", FarmMode.CONTRACT, "farmer", T0))
    assert not real.in_transaction
    assert s.get_profile("farm-1") is None  # the write did not survive
    s.save_profile(FarmProfile("farm-1", FarmMode.INDEPENDENT, "farmer", T0))  # next transaction works
    assert s.get_profile("farm-1").mode is FarmMode.INDEPENDENT


def test_incompatible_state_file_fails_loud(tmp_path):
    path = tmp_path / "clucktalk.sqlite3"
    SqliteStore(path).close()
    db = sqlite3.connect(path)
    db.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    db.commit()
    db.close()
    with pytest.raises(StoreError, match="reset-demo"):
        SqliteStore(path)


def test_timestamps_without_timezone_are_refused():
    with pytest.raises(ValueError, match="timezone"):
        SqliteStore().save_profile(FarmProfile("farm-1", FarmMode.CONTRACT, "farmer", datetime(2026, 9, 29)))


def test_treatments_have_no_dose_field_and_validate():
    """Safety (docs/DESIGN.md §7 rule 3): the record book can hold what was given, never how much."""
    names = {f.name for f in fields(Treatment)}
    assert names == {"kind", "name", "note"}
    for bad in ("", "   ", "x" * 81):
        with pytest.raises(ValueError):
            Treatment(TreatmentKind.MEDICINE, bad)
    with pytest.raises(ValueError):
        Treatment(TreatmentKind.VACCINE, "ND", "n" * 201)


def test_weight_sample_needs_a_weight():
    with pytest.raises(ValueError):
        DailyRecord(date(2026, 9, 29), 0, 10.0, weight_sample_birds=20)
    with pytest.raises(ValueError):
        DailyRecord(date(2026, 9, 29), 0, 10.0, avg_weight_g=900.0, weight_sample_birds=0)
