"""Step 52 part D: the backup stamp, the age of the last good backup in pilot-stats, and the hardening of the units."""

# ruff: noqa: F811  (the state fixture is imported from the deploy tests and used by name)
from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from clucktalk.usage import backup_report
from tests.harness.test_deploy_files import (  # noqa: F401  (the state fixture and helpers are shared)
    at,
    backup_sqlite,
    restore_test,
    settings,
    state,
    text,
)
from tests.harness.test_pilot_stats import make, run

ROOT = Path(__file__).resolve().parents[2]


# -- the report -------------------------------------------------------------------------------------------------------
def test_the_backup_report_shows_the_age_and_warns_after_26_hours():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

    def stamp(hours):
        return (now - timedelta(hours=hours)).isoformat()

    assert backup_report(stamp(2), now) == ["Last good backup: 2.0 hours ago"]
    assert backup_report(stamp(25.9), now) == ["Last good backup: 25.9 hours ago"]  # not yet late
    late = backup_report(stamp(26.1), now)
    assert late[0] == "Last good backup: 26.1 hours ago"
    assert late[1] == "WARNING: the last good backup is more than 26 hours old. Check clucktalk-backup."
    assert backup_report(stamp(100), now)[1].startswith("WARNING:")


def test_a_missing_damaged_or_future_stamp_is_a_warning_never_a_crash_or_a_good_age():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    for value in (None, "", "not a time", "2026-13-45T99:00:00+00:00", "2026-10-10T10:00:00"):  # the last: no zone
        out = backup_report(value, now)
        assert len(out) == 1 and out[0].startswith("WARNING:") and "hours ago" not in out[0], value
    future = backup_report((now + timedelta(hours=3)).isoformat(), now)
    assert future[0].startswith("WARNING:") and "future" in future[0]


def test_pilot_stats_with_backups_prints_the_age_and_without_it_prints_nothing_about_backups(tmp_path):
    usage = make(tmp_path)
    assert "backup" not in run(["--usage", str(usage)]).stdout.lower()
    folder = tmp_path / "backups"
    folder.mkdir()
    stamp = folder / "LAST_GOOD_BACKUP"
    stamp.write_text(
        (datetime.now(UTC) - timedelta(hours=3)).isoformat() + "\npilot_state_x.sqlite3\n", encoding="utf-8"
    )
    fresh = run(["--usage", str(usage), "--backups", str(folder)])
    assert fresh.returncode == 0 and "Last good backup: 3.0 hours ago" in fresh.stdout and "WARNING" not in fresh.stdout
    stamp.write_text((datetime.now(UTC) - timedelta(hours=40)).isoformat() + "\n", encoding="utf-8")
    late = run(["--usage", str(usage), "--backups", str(folder)])
    assert late.returncode == 0 and "WARNING: the last good backup is more than 26 hours old" in late.stdout
    stamp.unlink()
    none = run(["--usage", str(usage), "--backups", str(folder)])
    assert none.returncode == 0 and "WARNING: no backup stamp" in none.stdout


def test_the_stats_arguments_are_still_strict(tmp_path):
    usage = make(tmp_path)
    assert run(["--usage", str(usage), "--backups"]).returncode == 2
    assert run(["--usage", str(usage), "--bogus", "x"]).returncode == 2
    assert run(["--backups", str(tmp_path)]).returncode == 2  # the usage file is always named


def test_the_stats_command_still_runs_without_the_virtual_environment_packages():
    code = "import sys; sys.path.insert(0, 'src'); import clucktalk.usage as u; assert u.backup_report is not None"
    done = subprocess.run([sys.executable, "-S", "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr  # only the standard library is needed


# -- the stamp --------------------------------------------------------------------------------------------------------
def test_a_good_backup_writes_a_stamp_and_a_failed_one_leaves_the_old_stamp(state, tmp_path):
    dest = tmp_path / "b"
    made = backup_sqlite.backup(state, dest, 3, [], at(1))
    stamp = (dest / "LAST_GOOD_BACKUP").read_text(encoding="utf-8").splitlines()
    assert stamp == ["2026-10-09T02:30:01+00:00", made.name]
    with pytest.raises(SystemExit):
        backup_sqlite.backup(tmp_path / "nope.sqlite3", dest, 3, [], at(5))
    with pytest.raises(SystemExit, match="already exists"):
        backup_sqlite.backup(state, dest, 3, [], at(1))
    assert (dest / "LAST_GOOD_BACKUP").read_text(encoding="utf-8").splitlines() == stamp


def test_the_stamp_follows_the_newest_good_backup_and_is_not_a_backup_itself(state, tmp_path):
    dest = tmp_path / "b"
    backup_sqlite.backup(state, dest, 2, [], at(1))
    newest = backup_sqlite.backup(state, dest, 2, [], at(9))
    assert (dest / "LAST_GOOD_BACKUP").read_text(encoding="utf-8").splitlines()[1] == newest.name
    assert restore_test.newest(dest) == newest  # the stamp file is never taken for a backup
    assert not list(dest.glob("*.tmp"))  # written atomically


def test_a_backup_that_fails_its_integrity_check_does_not_move_the_stamp(state, tmp_path, monkeypatch):
    dest = tmp_path / "b"
    backup_sqlite.backup(state, dest, 3, [], at(1))
    before = (dest / "LAST_GOOD_BACKUP").read_text(encoding="utf-8")

    class Bad:
        def execute(self, sql):
            class Row:
                @staticmethod
                def fetchone():
                    return ("damaged",)

            return Row()

        def close(self):
            pass

    real = sqlite3.connect
    seen: list[str] = []

    def connect(path, *a, **k):
        # The copy is made through the first connection to the new file; the second one is the integrity check.
        if str(path).endswith("20261009-023002.sqlite3"):
            seen.append(str(path))
            if len(seen) == 2:
                return Bad()
        return real(path, *a, **k)

    monkeypatch.setattr(backup_sqlite.sqlite3, "connect", connect)
    with pytest.raises(SystemExit, match="integrity check"):
        backup_sqlite.backup(state, dest, 3, [], at(2))
    assert (dest / "LAST_GOOD_BACKUP").read_text(encoding="utf-8") == before


# -- the units --------------------------------------------------------------------------------------------------------
EXTRA_HARDENING = {
    "ProtectProc": ["invisible"],
    "ProcSubset": ["pid"],
    "PrivateUsers": ["true"],
    "RestrictSUIDSGID": ["true"],
    "LockPersonality": ["true"],
    "SystemCallArchitectures": ["native"],
    "RestrictNamespaces": ["true"],
    "ProtectKernelModules": ["true"],
    "ProtectKernelLogs": ["true"],
    "ProtectClock": ["true"],
    "ProtectHostname": ["true"],
    "RemoveIPC": ["true"],
}


@pytest.mark.parametrize("unit", ["clucktalk-pilot.service", "clucktalk-demo.service"])
def test_the_instance_units_have_the_extra_hardening_and_skip_the_two_that_can_break_python(unit):
    s = settings(unit)
    for key, value in EXTRA_HARDENING.items():
        assert s.get(key) == value, f"{unit}: {key}"
    assert "MemoryDenyWriteExecute" not in s and "SystemCallFilter" not in s
    body = text(unit)
    assert "MemoryDenyWriteExecute" in body and "SystemCallFilter" in body  # named in a comment, with the reason


def test_the_backup_unit_is_hardened_too():
    s = settings("clucktalk-backup.service")
    for key in ("NoNewPrivileges", "PrivateTmp", "ProtectHome", "ProtectSystem", "RestrictSUIDSGID", "LockPersonality"):
        assert key in s, key
    assert s["ProtectSystem"] == ["strict"]
