"""The committed card bundle must match its template, labels and font (scripts/build_cards.py --check)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_built_cards_are_up_to_date():
    r = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "build_cards.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_font_license_ships_with_the_font():
    fonts = ROOT / "ui" / "fonts"
    assert (fonts / "OFL.txt").read_text(encoding="utf-8").find("SIL OPEN FONT LICENSE Version 1.1") != -1
    assert (fonts / "README.md").exists()
