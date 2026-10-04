"""Step 49 part D: developer text about reset-demo matches what it does since Step 48C: it needs --yes, moves the live
state file to a backups folder and deletes only the demo-clock file. No message or comment says it just deletes or
restores."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src/clucktalk/server/app.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "src/clucktalk/config.py").read_text(encoding="utf-8")


def test_the_startup_line_says_yes_and_that_the_live_file_is_moved():
    lines = APP.splitlines()
    start = next(i for i, ln in enumerate(lines) if "Farm state:" in ln)
    line = " ".join(lines[start : start + 2])  # the print is wrapped over two lines
    assert "reset-demo --yes" in line and "moved" in line
    assert "restores" not in line and "deletes" not in line


def test_no_comment_says_reset_demo_deletes_the_state():
    for text in (APP, CONFIG):
        for number, line in enumerate(text.splitlines(), 1):
            if "reset-demo" in line:
                assert not re.search(r"reset-demo[^\n]*\b(deletes|restores|clears)\b", line), (number, line)
                assert not re.search(r"\b(deletes|restores)\b[^\n]*reset-demo", line), (number, line)


def test_the_config_comments_describe_the_move_and_the_one_deleted_file():
    assert "moves this" in CONFIG and "to a backups folder next to it" in CONFIG and "demo-clock" in CONFIG
    assert "reset-demo deletes only such a file" not in CONFIG
