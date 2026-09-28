"""`python tasks.py reset-demo` deletes the local farm state and nothing else (docs/DESIGN.md §13.1)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _reset(state_path: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLUCKTALK_STATE_PATH": str(state_path)}
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "tasks.py"), "reset-demo"], capture_output=True, text=True, cwd=ROOT, env=env
    )


def test_deletes_the_state_file_and_its_journal_only(tmp_path):
    state = tmp_path / "clucktalk.sqlite3"
    journal = tmp_path / "clucktalk.sqlite3-journal"
    neighbour = tmp_path / "notes.txt"
    for f in (state, journal, neighbour):
        f.write_bytes(b"x")
    r = _reset(state)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not state.exists() and not journal.exists() and neighbour.exists()
    assert "deleted" in r.stdout and "done" in r.stdout


def test_nothing_to_reset_is_not_an_error(tmp_path):
    r = _reset(tmp_path / "clucktalk.sqlite3")
    assert r.returncode == 0 and "nothing to reset" in r.stdout


def test_refuses_a_path_that_is_not_a_state_file(tmp_path):
    victim = tmp_path / "important.docx"
    victim.write_bytes(b"x")
    r = _reset(victim)
    assert r.returncode == 2 and victim.exists()
    assert ".sqlite3" in r.stderr  # config refuses the setting before anything is touched
