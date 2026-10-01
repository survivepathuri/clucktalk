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


# -- line endings: the build must not depend on how a checkout happens to store the template ---------------------------
def _build_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_cards", ROOT / "scripts" / "build_cards.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_crlf_template_builds_exactly_the_same_bytes_as_an_lf_template():
    """Found in CI (Step 47A-fix): a template saved with CRLF on Windows made the build skip its header line, so the
    bundle committed from that machine differed from every other machine's build."""
    mod = _build_module()
    for name, labels in mod.CARDS.items():
        lf = (mod.TEMPLATES / name).read_bytes().decode("utf-8").replace("\r\n", "\n")
        crlf = lf.replace("\n", "\r\n")
        assert mod.build(crlf, labels) == mod.build(lf, labels), name


def test_every_built_card_is_byte_identical_to_the_build_and_has_no_carriage_return():
    mod = _build_module()
    for name, labels in mod.CARDS.items():
        template = (mod.TEMPLATES / name).read_bytes().decode("utf-8")
        built = mod.build(template, labels).encode("utf-8")
        committed = (mod.CARDS_DIR / name).read_bytes()
        assert committed == built, name
        assert b"\r" not in committed, f"{name} contains a carriage return"
        assert b"<!-- Built by scripts/build_cards.py" in committed, name


def test_the_gitattributes_force_lf_for_the_generated_and_compared_text_files():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for pattern in ("src/clucktalk/server/cards/*.html", "ui/cards/*.html", "docs/EVALS.md", "docs/TELUGU_REVIEW.md",
                    "data/eval/golden_cases.json"):  # fmt: skip
        assert f"{pattern} text eol=lf" in attrs, pattern
