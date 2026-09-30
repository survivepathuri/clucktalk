"""SqliteStore: round trips, persistence across restarts, transactions, and loud failures (Rule 6)."""

from __future__ import annotations

import sqlite3
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from clucktalk.domain.models import DailyRecord, Treatment, TreatmentKind
from clucktalk.domain.profile import ContractTerms, FarmMode, FarmProfile
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


def test_contract_terms_round_trip_and_replace():
    s = SqliteStore()
    assert s.get_contract_terms("farm-1") is None
    t1 = ContractTerms("farm-1", Decimal("92"), Decimal("1.85"), Decimal("2"), Decimal("3"), T0)
    s.save_contract_terms(t1)
    assert s.get_contract_terms("farm-1") == t1
    t2 = ContractTerms("farm-1", Decimal("95"), Decimal("1.8"), Decimal("2"), Decimal("3"), T0)
    s.save_contract_terms(t2)
    assert s.get_contract_terms("farm-1") == t2
    assert s.get_contract_terms("farm-2") is None


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


V3_CONTRACT_TERMS = """
CREATE TABLE contract_terms (
    farm_id TEXT PRIMARY KEY, base_rate_per_kg TEXT NOT NULL, standard_fcr TEXT NOT NULL,
    mortality_allowance_pct TEXT NOT NULL, incentive_per_kg_per_fcr_point TEXT NOT NULL,
    deduction_per_kg_per_fcr_point TEXT NOT NULL, updated_at TEXT NOT NULL
)
"""


def _v3_state_file(path, *, with_terms: bool) -> None:
    """A state file as schema v3 wrote it: current tables, but contract_terms still with the retired column."""
    SqliteStore(path).close()
    db = sqlite3.connect(path)
    db.execute("DROP TABLE follow_up_answers")  # a real v3 file never had it (added in v5)
    db.execute("DROP TABLE contract_terms")
    db.execute(V3_CONTRACT_TERMS)
    if with_terms:
        db.execute(
            "INSERT INTO contract_terms VALUES ('farm-1', '92', '1.85', '5', '2', '3', '2026-09-29T00:00:00+00:00')"
        )
    db.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
    db.commit()
    db.close()


def test_a_v3_state_file_is_migrated_to_v4_keeping_the_four_numbers(tmp_path):
    path = tmp_path / "clucktalk.sqlite3"
    _v3_state_file(path, with_terms=True)
    store = SqliteStore(path)
    terms = store.get_contract_terms("farm-1")
    assert terms is not None
    assert (terms.base_rate_per_kg, terms.standard_fcr) == (Decimal("92"), Decimal("1.85"))
    assert (terms.incentive_per_kg_per_fcr_point, terms.deduction_per_kg_per_fcr_point) == (Decimal("2"), Decimal("3"))
    store.close()
    db = sqlite3.connect(path)
    # was "4": v5 is now the current schema, and a v3 file is migrated all the way to it
    assert db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "5"
    assert "mortality_allowance_pct" not in [r[1] for r in db.execute("PRAGMA table_info(contract_terms)")]
    db.close()
    SqliteStore(path).close()  # a second open of the migrated file is a no-op


def test_a_v3_state_file_without_terms_migrates_too(tmp_path):
    path = tmp_path / "clucktalk.sqlite3"
    _v3_state_file(path, with_terms=False)
    store = SqliteStore(path)
    assert store.get_contract_terms("farm-1") is None
    store.close()


def test_a_failed_migration_leaves_the_v3_file_untouched_and_fails_loud(tmp_path):
    path = tmp_path / "clucktalk.sqlite3"
    _v3_state_file(path, with_terms=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE contract_terms_v4 (blocker TEXT)")  # the migration's scratch table name is taken
    db.commit()
    db.close()
    with pytest.raises(StoreError, match="reset-demo"):
        SqliteStore(path)
    db = sqlite3.connect(path)
    assert db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "3"
    assert db.execute("SELECT mortality_allowance_pct FROM contract_terms").fetchone()[0] == "5"
    db.close()


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
