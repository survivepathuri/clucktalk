"""Step 48C part E: `python tasks.py reset-demo` never destroys real data silently. It lists what it would remove
(size and record counts), refuses without --yes, moves a state file that is not marked as a demo-clock file to
.local/backups with a timestamp instead of deleting it, and deletes only the demo-clock file."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tasks  # noqa: E402
from clucktalk.domain.models import DailyRecord  # noqa: E402
from clucktalk.store.sqlite import SqliteStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _farm(tmp_path: Path, records: int = 3, monkeypatch=None) -> tuple[Path, Path]:
    live, demo = tmp_path / "farm.sqlite3", tmp_path / "farm_demo_clock.sqlite3"
    store = SqliteStore(live)
    for i in range(records):
        store.put_record("farm-1", "house-1", DailyRecord(date(2026, 9, 1 + i), 1, 50.0))
    store.close()
    SqliteStore(demo, demo_clock=True).close()
    return live, demo


@pytest.fixture
def farm(monkeypatch, tmp_path):
    live, demo = _farm(tmp_path)
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(live))
    monkeypatch.setenv("MOCK_BEDROCK", "true")
    return live, demo


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_without_yes_nothing_changes_and_the_exit_code_says_so(farm, tmp_path, capsys):
    live, demo = farm
    before = (_sha(live), _sha(demo), _tree(tmp_path))
    assert tasks.reset_demo([]) == 2
    assert (_sha(live), _sha(demo), _tree(tmp_path)) == before
    streams = capsys.readouterr()
    assert "--yes" in streams.err
    assert not (tmp_path / "backups").exists()


def test_the_refusal_still_lists_each_file_with_its_size_and_its_record_counts(farm, capsys):
    live, demo = farm
    tasks.reset_demo([])
    out = capsys.readouterr().out
    assert str(live) in out and str(demo) in out
    assert f"{live.stat().st_size} bytes" in out and f"{demo.stat().st_size} bytes" in out
    assert "3 daily records" in out and "0 daily records" in out
    assert "will be MOVED" in out and "backups" in out and "will be deleted" in out and "demo-clock" in out


def test_with_yes_an_unmarked_state_file_is_moved_with_a_timestamp_and_never_deleted(farm, tmp_path):
    live, demo = farm
    digest = _sha(live)
    assert tasks.reset_demo(["--yes"]) == 0
    assert not live.exists()
    moved = sorted((tmp_path / "backups").glob("farm.*.sqlite3"))
    assert len(moved) == 1 and moved[0].name != "farm.sqlite3"
    assert _sha(moved[0]) == digest  # the very same bytes
    assert len(moved[0].name.split(".")[1]) == 15  # YYYYMMDD-HHMMSS


def test_with_yes_the_demo_clock_file_is_deleted_not_kept(farm, tmp_path):
    live, demo = farm
    assert tasks.reset_demo(["--yes"]) == 0
    assert not demo.exists()
    assert not list((tmp_path / "backups").glob("*demo_clock*"))


def test_the_journal_of_a_moved_file_moves_with_it(farm, tmp_path):
    live, _ = farm
    journal = live.with_name(live.name + "-journal")
    journal.write_bytes(b"j")
    assert tasks.reset_demo(["--yes"]) == 0
    assert not journal.exists()
    assert len(list((tmp_path / "backups").glob("farm.*.sqlite3-journal"))) == 1


def test_a_file_that_is_not_a_database_is_still_moved_and_described_honestly(monkeypatch, tmp_path, capsys):
    live = tmp_path / "farm.sqlite3"
    live.write_bytes(b"x" * 10)
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(live))
    tasks.reset_demo([])
    assert "not a readable database" in capsys.readouterr().out
    assert tasks.reset_demo(["--yes"]) == 0
    assert not live.exists() and len(list((tmp_path / "backups").iterdir())) == 1


def test_two_resets_in_a_row_keep_both_backups(monkeypatch, tmp_path):
    live = tmp_path / "farm.sqlite3"
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(live))
    for payload in (b"first", b"second"):
        live.write_bytes(payload)
        assert tasks.reset_demo(["--yes"]) == 0
    kept = sorted(p.read_bytes() for p in (tmp_path / "backups").iterdir())
    assert kept == [b"first", b"second"]


@pytest.mark.parametrize("args", [["--force"], ["yes"], ["--yes", "--yes"], ["--yes", "--all"], ["-y"]])
def test_any_other_argument_is_refused_and_changes_nothing(farm, tmp_path, args):
    live, demo = farm
    before = (_sha(live), _sha(demo), _tree(tmp_path))
    assert tasks.reset_demo(args) == 2
    assert (_sha(live), _sha(demo), _tree(tmp_path)) == before


def test_nothing_to_reset_needs_no_flag(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(tmp_path / "farm.sqlite3"))
    assert tasks.reset_demo([]) == 0
    assert "nothing to reset" in capsys.readouterr().out


def test_the_command_line_passes_the_flag_on_and_refuses_without_it(tmp_path):
    live, demo = _farm(tmp_path)
    env = {**os.environ, "CLUCKTALK_STATE_PATH": str(live)}
    cmd = [sys.executable, "-B", str(ROOT / "tasks.py"), "reset-demo"]
    before = _sha(live)
    refused = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
    assert refused.returncode == 2 and live.exists() and _sha(live) == before
    done = subprocess.run([*cmd, "--yes"], capture_output=True, text=True, cwd=ROOT, env=env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert not live.exists() and not demo.exists() and len(list((tmp_path / "backups").iterdir())) == 1


def test_a_refusal_never_touches_a_live_file_even_when_the_demo_clock_file_is_missing(monkeypatch, tmp_path):
    live, demo = _farm(tmp_path)
    demo.unlink()
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(live))
    before = _sha(live)
    assert tasks.reset_demo([]) == 2 and _sha(live) == before


def test_an_unknown_argument_is_refused_even_when_there_is_nothing_to_reset(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(tmp_path / "farm.sqlite3"))
    assert tasks.reset_demo(["--force"]) == 2
    assert "only option is --yes" in capsys.readouterr().err
