"""Step 51 part E: the deploy templates and the backup and restore scripts. Templates only: nothing here calls AWS
or any network. The two instances are separate users with separate state and ports; the env example holds
placeholders only; the backup is an online SQLite backup that is checked, kept private and pruned; the restore
test proves a backup opens and fails on a damaged one."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
sys.path.insert(0, str(DEPLOY))

import backup_sqlite  # noqa: E402
import restore_test  # noqa: E402

from clucktalk.store.sqlite import SqliteStore  # noqa: E402


def text(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def settings(unit: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in text(unit).splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out.setdefault(key.strip(), []).append(value.strip())
    return out


# -- templates -------------------------------------------------------------------------------------------------------
def test_the_two_units_are_separate_users_with_separate_state_environment_and_ports():
    pilot, demo = settings("clucktalk-pilot.service"), settings("clucktalk-demo.service")
    assert pilot["User"] != demo["User"] and pilot["EnvironmentFile"] != demo["EnvironmentFile"]
    assert pilot["ReadWritePaths"] != demo["ReadWritePaths"]
    assert (
        "pilot" in pilot["User"][0] and "pilot" in pilot["ReadWritePaths"][0] and "pilot" in pilot["EnvironmentFile"][0]
    )
    assert (
        "demo" in demo["User"][0] and "demo" in demo["ReadWritePaths"][0] and "pilot" not in demo["ReadWritePaths"][0]
    )
    for unit in (pilot, demo):
        assert unit["ProtectSystem"] == ["strict"] and unit["NoNewPrivileges"] == ["true"] and unit["UMask"] == ["0077"]
        assert unit["ExecStart"] == ["/opt/clucktalk/.venv/bin/python scripts/run_instance.py"]
        assert unit["Restart"] == ["on-failure"]


def test_the_env_example_has_placeholders_only_and_the_two_instances_never_share_a_path_or_a_port():
    env = text("env.example")
    token_values = re.findall(r"^#? ?CLUCKTALK_[A-Z_]*TOKENS?=(.*)$", env, re.M)
    assert len(token_values) >= 3
    assert all(v.strip().startswith("<") and v.strip().endswith(">") for v in token_values), token_values
    assert not re.findall(r"=\s*([A-Za-z0-9_-]{32,})\s*$", env, re.M), "a value that looks like a real secret"
    pilot_block, demo_block = env.split("# ===== /etc/clucktalk/demo.env")

    def paths(block: str) -> set[str]:
        return set(re.findall(r"=(/var/lib/\S+)", block))

    def ports(block: str) -> set[str]:
        return set(re.findall(r"PORT=(\d+)", block))

    assert paths(pilot_block).isdisjoint(paths(demo_block)) and ports(pilot_block).isdisjoint(ports(demo_block))
    active_pilot = re.sub(r"(?m)^#.*$", "", pilot_block)
    assert "CLUCKTALK_MODE=pilot" in active_pilot and "CLUCKTALK_WEATHER_LIVE" not in active_pilot  # live weather: off


def test_the_caddy_template_opens_nothing_but_the_two_sites_and_logs_no_requests():
    caddy = text("Caddyfile.template")
    assert caddy.count("reverse_proxy") == 2 and "127.0.0.1:8766" in caddy and "127.0.0.1:8776" in caddy
    assert "admin off" in caddy and "log" not in re.sub(r"(?m)^\s*#.*$", "", caddy).replace("login", "")
    assert re.findall(r"^(\S+) \{$", caddy, re.M) == ["PILOT_HOST", "DEMO_HOST"] or "PILOT_HOST" in caddy


def test_the_backup_unit_runs_the_restore_test_after_every_backup():
    unit = settings("clucktalk-backup.service")
    assert [c.split()[:2] for c in unit["ExecStart"]] == [
        ["/opt/clucktalk/.venv/bin/python", "deploy/backup_sqlite.py"],
        ["/opt/clucktalk/.venv/bin/python", "deploy/restore_test.py"],
    ]
    assert unit["Type"] == ["oneshot"] and unit["User"] == ["clucktalk-pilot"]
    assert "OnCalendar=*-*-* 02:30:00" in text("clucktalk-backup.timer") and "Persistent=true" in text(
        "clucktalk-backup.timer"
    )


def test_nothing_in_deploy_or_the_launcher_reaches_for_aws_or_the_network():
    files = [*(p for p in DEPLOY.iterdir() if p.is_file()), ROOT / "scripts" / "run_instance.py"]
    for path in files:
        body = path.read_text(encoding="utf-8")
        code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
        assert not re.search(r"boto3|import requests|urllib\.request|httpx|\baws\s+(s3|ec2|lightsail)\b", code), (
            path.name
        )


# -- backup and restore ----------------------------------------------------------------------------------------------
@pytest.fixture
def state(tmp_path) -> Path:
    path = tmp_path / "state" / "pilot_state.sqlite3"
    path.parent.mkdir()
    store = SqliteStore(path)
    store.close()
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS probe (n INTEGER)")
    db.executemany("INSERT INTO probe VALUES (?)", [(i,) for i in range(5)])
    db.commit()
    db.close()
    return path


def at(second: int) -> datetime:
    return datetime(2026, 10, 9, 2, 30, second, tzinfo=UTC)


def test_a_backup_is_an_online_copy_with_the_same_rows_private_to_its_owner(state, tmp_path):
    dest = tmp_path / "backups"
    made = backup_sqlite.backup(state, dest, keep=14, also=[], now=at(1))
    assert made.name == "pilot_state_20261009-023001.sqlite3"
    assert restore_test.tables(made)["probe"] == 5 == restore_test.tables(state)["probe"]
    if os.name != "nt":
        assert made.stat().st_mode & 0o777 == 0o600


def test_a_backup_taken_while_the_live_file_is_open_for_writing_is_still_whole(state, tmp_path):
    live = sqlite3.connect(state)
    live.execute("BEGIN IMMEDIATE")
    live.execute("INSERT INTO probe VALUES (99)")  # an uncommitted write in progress
    made = backup_sqlite.backup(state, tmp_path / "b", keep=3, also=[], now=at(2))
    live.rollback()
    live.close()
    assert restore_test.tables(made)["probe"] == 5  # committed rows only; never a torn file


def test_old_backups_are_pruned_and_the_files_saved_with_them(state, tmp_path):
    usage = tmp_path / "state" / "usage_pilot.json"
    usage.write_text("{}", encoding="utf-8")
    dest = tmp_path / "b"
    for s in range(1, 6):
        backup_sqlite.backup(state, dest, keep=2, also=[usage], now=at(s))
    kept = sorted(p.name for p in dest.iterdir())
    assert kept == [
        "pilot_state_20261009-023004.sqlite3",
        "pilot_state_20261009-023005.sqlite3",
        "usage_pilot_20261009-023004.json",
        "usage_pilot_20261009-023005.json",
    ]


def test_backup_refuses_a_missing_state_two_in_a_second_and_a_zero_keep(state, tmp_path):
    with pytest.raises(SystemExit, match="no state file"):
        backup_sqlite.backup(tmp_path / "nope.sqlite3", tmp_path / "b", 3, [], at(1))
    backup_sqlite.backup(state, tmp_path / "b", 3, [], at(1))
    with pytest.raises(SystemExit, match="already exists"):
        backup_sqlite.backup(state, tmp_path / "b", 3, [], at(1))
    with pytest.raises(SystemExit, match="keep"):
        backup_sqlite.backup(state, tmp_path / "c", 0, [], at(1))


def test_the_restore_test_passes_on_a_good_backup_and_prints_counts_never_rows(state, tmp_path):
    dest = tmp_path / "b"
    backup_sqlite.backup(state, dest, 3, [], at(1))
    done = subprocess.run(
        [sys.executable, str(DEPLOY / "restore_test.py"), "--dest", str(dest), "--live", str(state)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr
    assert "restore test: PASS" in done.stdout and "probe: 5 row(s)" in done.stdout
    assert "99" not in done.stdout.replace("20261009", "")


def test_the_restore_test_uses_the_newest_backup(state, tmp_path):
    dest = tmp_path / "b"
    backup_sqlite.backup(state, dest, 5, [], at(1))
    db = sqlite3.connect(state)
    db.execute("INSERT INTO probe VALUES (7)")
    db.commit()
    db.close()
    backup_sqlite.backup(state, dest, 5, [], at(2))
    assert restore_test.tables(restore_test.newest(dest))["probe"] == 6


def test_the_restore_test_fails_on_a_damaged_empty_or_missing_backup_and_never_touches_the_live_file(state, tmp_path):
    dest = tmp_path / "b"
    made = backup_sqlite.backup(state, dest, 3, [], at(1))
    before = state.read_bytes()
    made.write_bytes(made.read_bytes()[:512] + b"\x00" * 4096)
    with pytest.raises(SystemExit):
        restore_test.restore_test(made, state)
    (dest / "z_empty.sqlite3").write_bytes(b"")
    with pytest.raises(SystemExit):
        restore_test.restore_test(dest / "z_empty.sqlite3", state)
    with pytest.raises(SystemExit, match="no such backup"):
        restore_test.restore_test(dest / "missing.sqlite3", state)
    with pytest.raises(SystemExit, match="no backup"):
        restore_test.newest(tmp_path / "nothing-here")
    assert state.read_bytes() == before


def test_the_restore_test_notices_a_backup_that_lacks_a_table_the_live_file_has(state, tmp_path):
    made = backup_sqlite.backup(state, tmp_path / "b", 3, [], at(1))
    db = sqlite3.connect(state)
    db.execute("CREATE TABLE added_later (x)")
    db.commit()
    db.close()
    with pytest.raises(SystemExit, match="added_later"):
        restore_test.restore_test(made, state)


# -- the launcher ----------------------------------------------------------------------------------------------------
def test_the_launcher_stops_with_a_failure_when_an_instance_refuses_to_start(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLUCKTALK_")}
    env.update(
        MOCK_BEDROCK="true", CLUCKTALK_MODE="pilot", PYTHONIOENCODING="utf-8"
    )  # no farm file, no token, no state
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_instance.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=ROOT,
        timeout=60,
    )
    assert done.returncode != 0
    assert "CLUCKTALK_PILOT_FARM_PATH" in done.stderr or "CLUCKTALK_SIMULATOR_TOKENS" in done.stderr


def test_a_child_that_stops_by_itself_is_a_failure_even_with_exit_code_zero():
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_instance

    assert run_instance.failure_code(0) == 1 and run_instance.failure_code(None) == 1
    assert run_instance.failure_code(2) == 2 and run_instance.failure_code(-15) == -15


def test_a_database_that_says_something_other_than_ok_fails_the_restore_test(state, tmp_path, monkeypatch):
    made = backup_sqlite.backup(state, tmp_path / "b", 3, [], at(1))

    class Corrupt:
        def execute(self, sql):
            class Row:
                @staticmethod
                def fetchone():
                    return ("row 3 missing from index probe_idx",)

            return Row()

        def close(self):
            pass

    real = sqlite3.connect
    monkeypatch.setattr(
        restore_test.sqlite3,
        "connect",
        lambda path, *a, **k: (
            Corrupt() if str(path) != str(made) and str(path).endswith(made.name) else real(path, *a, **k)
        ),
    )
    with pytest.raises(SystemExit, match="integrity check failed"):
        restore_test.restore_test(made, None)


def test_a_valid_database_that_is_not_ours_fails_the_restore_test(tmp_path):
    other = tmp_path / "other.sqlite3"
    db = sqlite3.connect(other)
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO meta VALUES ('schema_version', '999')")  # a schema this code does not know
    db.commit()
    db.close()
    with pytest.raises(SystemExit, match="could not open"):
        restore_test.restore_test(other, None)


def test_the_backup_includes_rows_that_only_live_in_the_write_ahead_log(tmp_path):
    path = tmp_path / "wal_state.sqlite3"
    live = sqlite3.connect(path)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("PRAGMA wal_autocheckpoint=0")
    live.execute("CREATE TABLE probe (n INTEGER)")
    live.executemany("INSERT INTO probe VALUES (?)", [(i,) for i in range(6)])
    live.commit()  # committed, but still in the -wal file: a plain copy of the main file would miss it
    made = backup_sqlite.backup(path, tmp_path / "b", 3, [], at(3))
    live.close()
    assert restore_test.tables(made)["probe"] == 6
