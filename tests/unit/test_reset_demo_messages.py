"""Step 48D part C: every developer message that tells you to run reset-demo says --yes, because reset-demo without it
only lists the files and changes nothing (Step 48C). Developer CLI text, not farmer-facing."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from clucktalk.store import StoreError
from clucktalk.store.sqlite import SqliteStore

ROOT = Path(__file__).resolve().parents[2]
FILES = ("src/clucktalk/store/sqlite.py", "scripts/demo_three_days.py")


@pytest.mark.parametrize("name", FILES)
def test_every_instruction_to_run_reset_demo_in_these_files_says_yes(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    found = re.findall(r"python tasks\.py reset-demo[^\"\n]*", text)
    assert found, name
    assert all(f.startswith("python tasks.py reset-demo --yes") for f in found), found


def test_a_schema_mismatch_says_how_to_reset(tmp_path):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path).close()
    db = sqlite3.connect(path)
    db.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    db.commit()
    db.close()
    with pytest.raises(StoreError, match="reset-demo --yes"):
        SqliteStore(path)


def test_a_demo_clock_file_without_the_clock_says_how_to_clear_it(tmp_path):
    path = tmp_path / "d.sqlite3"
    SqliteStore(path, demo_clock=True).close()
    with pytest.raises(StoreError, match="reset-demo --yes"):
        SqliteStore(path)
