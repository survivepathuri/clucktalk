"""Schema v5: the append-only ``follow_up_answers`` table, the v3/v4 -> v5 migrations, restart behaviour
(docs/DESIGN.md §18). Real SQLite files (tmp_path) wherever a restart or a migration is tested."""

from __future__ import annotations

import inspect
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from decimal import Decimal

import pytest

from clucktalk.domain.follow_up import (
    FollowUpAnswer,
    FollowUpState,
    Outcome,
    follow_up_state,
    new_answer_id,
)
from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.triage import (
    CheckStatus,
    Floor,
    HealthCheck,
    Sign,
    TriageInput,
    TriageResult,
    Urgency,
    new_check_id,
)
from clucktalk.store import Store, StoreError
from clucktalk.store import sqlite as sqlite_module
from clucktalk.store.sqlite import SqliteStore

IST = timezone(timedelta(hours=5, minutes=30))
CHECK_DAY = date(2026, 10, 10)
AT = datetime.combine(CHECK_DAY, dtime(10, 0), tzinfo=IST)
INP = TriageInput("house-1", "House 1", "షెడ్ 1", "Ross 308", 40, 900, (Sign.COUGHING,), None, None, None,
                  2, 1.0, False, None, CHECK_DAY.isoformat())  # fmt: skip
ANSWER_COLUMNS = ["answer_id", "farm_id", "house_id", "check_id", "said", "records_worse", "proposal_id", "answered_at"]


def _check(urgency=Urgency.WATCH) -> HealthCheck:
    result = TriageResult(urgency, (), (), "rules", None, None)
    return HealthCheck(new_check_id(), "farm", "house-1", AT, CheckStatus.READY, INP, Floor(urgency, ()), result, AT)


def _answer(check: HealthCheck, said=Outcome.BETTER, *, days=3, hours=0, farm="farm") -> FollowUpAnswer:
    return FollowUpAnswer(
        new_answer_id(), farm, check.house_id, check.check_id, said, False, "prop_" + "c" * 16,
        check.created_at + timedelta(days=days, hours=hours),
    )  # fmt: skip


def _version(path) -> str:
    db = sqlite3.connect(path)
    try:
        return db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]
    finally:
        db.close()


def _snapshot(path) -> tuple:
    """Everything a failed migration must leave alone: the schema text and every row of every table."""
    db = sqlite3.connect(path)
    try:
        schema = db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        rows = {
            name: db.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall()
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            if not name.startswith("sqlite_")
        }
        return schema, rows
    finally:
        db.close()


def _make_v4_file(path, *, with_data: bool = True) -> HealthCheck | None:
    """A state file exactly as schema v4 left it: no follow_up_answers table, version 4."""
    store = SqliteStore(path)
    check = None
    if with_data:
        check = _check(Urgency.URGENT)
        store.add_health_check(check)
        store.put_record("farm", "house-1", DailyRecord(CHECK_DAY, 4, 120.0))
    store.close()
    db = sqlite3.connect(path)
    db.execute("DROP TABLE follow_up_answers")
    db.execute("UPDATE meta SET value = '4' WHERE key = 'schema_version'")
    db.commit()
    db.close()
    return check


V3_CONTRACT_TERMS = """
CREATE TABLE contract_terms (
    farm_id TEXT PRIMARY KEY, base_rate_per_kg TEXT NOT NULL, standard_fcr TEXT NOT NULL,
    mortality_allowance_pct TEXT NOT NULL, incentive_per_kg_per_fcr_point TEXT NOT NULL,
    deduction_per_kg_per_fcr_point TEXT NOT NULL, updated_at TEXT NOT NULL
)
"""


def _make_v3_file(path) -> HealthCheck:
    check = _make_v4_file(path)
    db = sqlite3.connect(path)
    db.execute("DROP TABLE contract_terms")
    db.execute(V3_CONTRACT_TERMS)
    db.execute("INSERT INTO contract_terms VALUES ('farm', '92', '1.85', '5', '2', '3', '2026-09-29T00:00:00+00:00')")
    db.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
    db.commit()
    db.close()
    assert check is not None
    return check


# -- the table -------------------------------------------------------------------------------------------------------
def test_a_fresh_store_is_schema_v5_with_the_answers_table(tmp_path):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path).close()
    assert _version(path) == "5" and sqlite_module.SCHEMA_VERSION == "5"
    db = sqlite3.connect(path)
    assert [r[1] for r in db.execute("PRAGMA table_info(follow_up_answers)")] == ANSWER_COLUMNS
    db.close()


def test_answers_round_trip_per_farm_and_check_in_the_order_they_were_given():
    s = SqliteStore()
    a, b = _check(), _check()
    first, second, third = _answer(a, Outcome.WORSE, hours=1), _answer(a, Outcome.BETTER, hours=2), _answer(b)
    for x in (second, first, third):  # stored out of order on purpose
        s.add_follow_up_answer(x)
    assert s.follow_up_answers("farm", a.check_id) == (first, second)
    assert s.follow_up_answers("farm", b.check_id) == (third,)
    assert s.follow_up_answers("other-farm", a.check_id) == ()
    assert s.follow_up_answers("farm", new_check_id()) == ()


def test_two_answers_at_the_same_instant_keep_their_insert_order():
    s = SqliteStore()
    c = _check()
    x, y = _answer(c, Outcome.SAME), _answer(c, Outcome.BETTER)  # same answered_at
    s.add_follow_up_answer(x)
    s.add_follow_up_answer(y)
    assert s.follow_up_answers("farm", c.check_id) == (x, y)


def test_the_table_has_no_free_text_column_and_the_closed_lists_are_enforced_by_the_database_too():
    s = SqliteStore()
    cols = {r["name"]: r["type"] for r in s._db.execute("PRAGMA table_info(follow_up_answers)")}
    assert list(cols) == ANSWER_COLUMNS
    assert set(cols.values()) == {"TEXT", "INTEGER"}  # no BLOB / JSON blob to hide words in
    assert not [c for c in cols if any(w in c for w in ("note", "text", "comment", "words", "message", "json"))]
    row = ("fu_" + "0" * 16, "farm", "house-1", new_check_id(), "", 0, "prop_" + "0" * 16, AT.isoformat())
    insert = "INSERT INTO follow_up_answers VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    for bad_said in ("it is fine now", "", "Better", "BETTER", None):
        with pytest.raises(sqlite3.IntegrityError):
            s._db.execute(insert, (*row[:4], bad_said, *row[5:]))
    with pytest.raises(sqlite3.IntegrityError):
        s._db.execute(insert, (*row[:4], "better", 2, *row[6:]))
    s._db.execute(insert, (*row[:4], "not_sure", 1, *row[6:]))  # a legal row does go in


def test_there_is_no_update_or_delete_for_answers_anywhere():
    api = {n for n in dir(SqliteStore) if "follow_up" in n and not n.startswith("_")}
    assert api == {"add_follow_up_answer", "follow_up_answers"}
    protocol = {n for n in dir(Store) if "follow_up" in n}
    assert protocol == {"add_follow_up_answer", "follow_up_answers"}
    source = inspect.getsource(sqlite_module).lower()
    for forbidden in ("update follow_up_answers", "delete from follow_up_answers", "replace into follow_up_answers",
                      "drop table follow_up_answers", "alter table follow_up_answers"):  # fmt: skip
        assert forbidden not in source


def test_an_existing_answer_is_never_replaced():
    s = SqliteStore()
    c = _check()
    a = _answer(c, Outcome.WORSE)
    s.add_follow_up_answer(a)
    with pytest.raises(sqlite3.IntegrityError):
        s.add_follow_up_answer(replace(a, said=Outcome.BETTER))  # same answer_id, a softer answer
    assert s.follow_up_answers("farm", c.check_id) == (a,)


def test_an_answer_with_no_timezone_is_refused_by_the_dataclass_so_it_never_reaches_the_store():
    c = _check()
    with pytest.raises(ValueError, match="timezone"):
        replace(_answer(c), answered_at=datetime(2026, 10, 13, 9, 0))


def test_answers_join_a_transaction_and_roll_back_with_it():
    s = SqliteStore()
    c = _check()
    with pytest.raises(RuntimeError), s.atomic():
        s.add_follow_up_answer(_answer(c))
        raise RuntimeError("boom")
    assert s.follow_up_answers("farm", c.check_id) == ()


# -- restart: the state is identical after closing and reopening a real file ------------------------------------------
def _house() -> House:
    records, day = [], date(2026, 9, 1)
    while day <= date(2026, 11, 30):
        records.append(DailyRecord(day, 2, 100.0))
        day += timedelta(days=1)
    return House("house-1", 1, HouseKind.BROILER, "Ross 308", date(2026, 9, 1), 5000, 0, 500.0, tuple(records))


def _derive(store: SqliteStore, check_id: str, today: date):
    check = store.get_health_check(check_id)
    assert check is not None
    handed = frozenset([check_id]) if store.handoff_for_check(check_id) else frozenset()
    answers = store.follow_up_answers(check.farm_id, check_id)
    return follow_up_state(
        check, answers, handed, _house(), today, store.recent_health_checks("farm", "house-1", date(2026, 1, 1))
    )


def test_the_follow_up_state_is_identical_after_a_restart_on_a_real_file(tmp_path):
    path = tmp_path / "state" / "clucktalk.sqlite3"
    s = SqliteStore(path)
    check = _check(Urgency.WATCH)
    s.add_health_check(check)
    today = CHECK_DAY + timedelta(days=4)
    due = _derive(s, check.check_id, today)
    assert due.state is FollowUpState.DUE
    worse = _answer(check, Outcome.WORSE, hours=1)
    better = _answer(check, Outcome.BETTER, hours=2)
    s.add_follow_up_answer(worse)
    s.add_follow_up_answer(better)
    before = _derive(s, check.check_id, today)
    before_answers = s.follow_up_answers("farm", check.check_id)
    assert before.state is FollowUpState.ESCALATED and before.outcome is Outcome.WORSE
    s.close()

    again = SqliteStore(path)
    assert again.follow_up_answers("farm", check.check_id) == before_answers == (worse, better)
    assert _derive(again, check.check_id, today) == before
    again.close()
    third = SqliteStore(path)  # and once more: a reopen changes nothing
    assert _derive(third, check.check_id, today) == before
    third.close()


def test_a_later_clock_changes_the_state_of_the_same_stored_answers_and_only_through_the_clock(tmp_path):
    path = tmp_path / "s.sqlite3"
    s = SqliteStore(path)
    check = _check(Urgency.URGENT)
    s.add_health_check(check)
    s.close()
    s = SqliteStore(path)
    assert _derive(s, check.check_id, CHECK_DAY).state is FollowUpState.SCHEDULED
    assert _derive(s, check.check_id, CHECK_DAY + timedelta(days=1)).state is FollowUpState.DUE
    assert _derive(s, check.check_id, CHECK_DAY + timedelta(days=9)).state is FollowUpState.LAPSED
    s.close()


# -- migrations: v4 -> v5 and v3 -> v5, each in one transaction --------------------------------------------------------
def test_a_v4_file_is_migrated_to_v5_keeping_everything(tmp_path):
    path = tmp_path / "s.sqlite3"
    check = _make_v4_file(path)
    assert _version(path) == "4"
    store = SqliteStore(path)
    assert store.get_health_check(check.check_id) == check
    assert store.records("farm", "house-1") == (DailyRecord(CHECK_DAY, 4, 120.0),)
    assert store.follow_up_answers("farm", check.check_id) == ()
    answer = _answer(check)
    store.add_follow_up_answer(answer)
    store.close()
    assert _version(path) == "5"
    again = SqliteStore(path)  # a second open of the migrated file is a no-op that keeps the answer
    assert again.follow_up_answers("farm", check.check_id) == (answer,)
    again.close()


def test_a_v3_file_is_migrated_to_v5_in_one_open_keeping_the_four_contract_numbers(tmp_path):
    path = tmp_path / "s.sqlite3"
    check = _make_v3_file(path)
    store = SqliteStore(path)
    terms = store.get_contract_terms("farm")
    assert terms is not None and terms.base_rate_per_kg == Decimal("92") and terms.standard_fcr == Decimal("1.85")
    assert store.get_health_check(check.check_id) == check
    assert store.follow_up_answers("farm", check.check_id) == ()
    store.close()
    db = sqlite3.connect(path)
    assert "mortality_allowance_pct" not in [r[1] for r in db.execute("PRAGMA table_info(contract_terms)")]
    assert [r[1] for r in db.execute("PRAGMA table_info(follow_up_answers)")] == ANSWER_COLUMNS
    db.close()
    assert _version(path) == "5"


def _block_follow_up_table(path) -> None:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE follow_up_answers (blocker TEXT)")  # a leftover table the migration cannot create over
    db.commit()
    db.close()


def test_a_failed_v4_to_v5_migration_changes_nothing_fails_loud_and_says_how_to_recover(tmp_path):
    path = tmp_path / "s.sqlite3"
    _make_v4_file(path)
    _block_follow_up_table(path)
    before = _snapshot(path)
    with pytest.raises(StoreError, match="reset-demo") as err:
        SqliteStore(path)
    assert "4" in str(err.value) and "5" in str(err.value) and "Nothing was changed" in str(err.value)
    assert _snapshot(path) == before
    assert _version(path) == "4"


def test_a_failed_migration_from_v3_undoes_the_v3_to_v4_step_too(tmp_path):
    """One transaction for the whole chain: if the last step fails, the first step is rolled back with it."""
    path = tmp_path / "s.sqlite3"
    _make_v3_file(path)
    _block_follow_up_table(path)
    before = _snapshot(path)
    with pytest.raises(StoreError, match="reset-demo"):
        SqliteStore(path)
    assert _snapshot(path) == before
    assert _version(path) == "3"
    db = sqlite3.connect(path)
    assert db.execute("SELECT mortality_allowance_pct FROM contract_terms").fetchone()[0] == "5"
    db.close()


@pytest.mark.parametrize("version", ["1", "2", "6", "10", "999", "five", ""])
def test_any_other_schema_version_still_fails_loud(tmp_path, version):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path).close()
    db = sqlite3.connect(path)
    db.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (version,))
    db.commit()
    db.close()
    before = _snapshot(path)
    with pytest.raises(StoreError, match="reset-demo"):
        SqliteStore(path)
    assert _snapshot(path) == before


def test_an_older_build_cannot_silently_open_a_v5_file(tmp_path, monkeypatch):
    """A build whose schema is older than the file's (the v4 release, simulated by its version constant) refuses the
    file with the reset message instead of ignoring the stored answers."""
    path = tmp_path / "s.sqlite3"
    s = SqliteStore(path)
    check = _check()
    s.add_health_check(check)
    answer = _answer(check, Outcome.WORSE)
    s.add_follow_up_answer(answer)
    s.close()
    before = _snapshot(path)
    monkeypatch.setattr(sqlite_module, "SCHEMA_VERSION", "4")
    with pytest.raises(StoreError, match="reset-demo") as err:
        SqliteStore(path)
    assert "schema 5" in str(err.value)
    monkeypatch.undo()
    assert _snapshot(path) == before  # refused without touching the file
    again = SqliteStore(path)
    assert again.follow_up_answers("farm", check.check_id) == (answer,)
    again.close()
