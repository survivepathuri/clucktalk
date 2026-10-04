"""Step 49 part D: NOTICE is checked against the installed packages on EVERY operating system the CI runs on (ubuntu and
windows), not only where it was generated. A pinned package that is missing or at another version fails the test; a
package its platform marker excludes (pywin32 on Linux) may be reported "not installed on this platform"; every other
row of a fresh NOTICE must equal the committed one. NOTICE and README say which system generated the committed file."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import tasks  # noqa: E402

NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
README = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())


def rows(text: str) -> dict[str, str]:
    found = {}
    for line in text.splitlines():
        m = re.match(r"^(\S+) (\S+) \| ", line)
        if m:
            found[tasks._norm(m.group(1))] = line
    return found


def marker_names() -> set[str]:
    names = set()
    for lines in tasks._requirement_files().values():
        for line in lines:
            clean = line.split("#")[0].strip()
            if ";" in clean:
                names.add(tasks._norm(clean.split(";")[0].split("==")[0].strip()))
    return names


@pytest.fixture(scope="module")
def fresh() -> str:
    return tasks.generate_notice()  # raises NoticeError when a pinned package is missing or at another version


def test_no_pinned_package_is_reported_not_installed_except_one_a_platform_marker_excludes(fresh):
    missing = {n for n, line in rows(fresh).items() if "not installed" in line}
    assert missing <= marker_names(), sorted(missing - marker_names())


def test_every_package_row_of_a_fresh_notice_equals_the_committed_one(fresh):
    committed, generated = rows(NOTICE), rows(fresh)
    skip = marker_names()
    assert {n for n in committed if n not in skip} == {n for n in generated if n not in skip}
    different = [n for n in generated if n not in skip and generated[n] != committed[n]]
    assert different == [], f"NOTICE is out of date for {different}: run python tasks.py notices"


def test_the_fresh_notice_names_the_system_it_was_generated_on(fresh):
    assert re.search(r"^Generated on: (Windows|Linux|macOS) ", fresh, re.M)


def test_the_committed_notice_and_the_readme_say_which_system_generated_it():
    m = re.search(r"^Generated on: (Windows|Linux|macOS) ", NOTICE, re.M)
    assert m, "run python tasks.py notices"
    assert "NOTICE" in README and f"generated on {m.group(1)}" in README
    assert "checked against the installed packages on every operating system the CI runs on" in README


def test_build_notice_writes_the_generated_on_line_only_when_given():
    lookup = {"a": {"version": "1", "expression": "MIT", "license": None, "classifiers": []}}
    with_os = tasks.build_notice("MIT License", {"r.txt": ["a==1"]}, lookup, "Linux")
    without = tasks.build_notice("MIT License", {"r.txt": ["a==1"]}, lookup)
    assert "Generated on: Linux (" in with_os and "Generated on" not in without


def test_the_readme_says_the_sale_window_hint_is_on_the_briefing_only():
    assert "sale-window hint" in README
    assert "shows on the daily briefing only" in README and "never raises a shed's health status" in README
