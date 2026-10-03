"""Step 48C part D: every live entry of the friction log (FRICTION_LOG.md and docs/DEV_NOTES.md) carries the six
official fields (task attempted, steps taken, expected vs actual, severity, workaround, actionable suggestion) plus
date, tag, time cost and reproduce, and its severity is exactly High, Medium or Low. A pointer entry (a number kept
valid after a merge or a move) holds one "Moved to" or "Merged into" line and nothing else."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "FRICTION_LOG.md": re.compile(r"(?m)^### (FL-\d{3}):[^\n]*\n"),
    "docs/DEV_NOTES.md": re.compile(r"(?m)^## (FL-\d{3}):[^\n]*\n"),
}
REQUIRED = (
    "Date",
    "Tag",
    "Task attempted",
    "Steps taken",
    "Expected vs actual",
    "Severity",
    "Workaround",
    "Actionable suggestion",
    "Time cost",
    "Reproduce",
)
SEVERITIES = {"High", "Medium", "Low"}
POINTER = re.compile(r"^(Moved to|Merged into) ")


def _entries() -> list[tuple[str, str, str]]:
    """(file, FL id, body) for every entry, in file order."""
    found: list[tuple[str, str, str]] = []
    for name, heading in FILES.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        marks = list(heading.finditer(text))
        # an entry ends at the next heading or at a horizontal rule
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = re.split(r"(?m)^---\s*$", text[m.end() : end])[0]
            found.append((name, m.group(1), body.strip()))
    return found


def _fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        m = re.match(r"^([A-Z][A-Za-z /]{1,40}):\s*(.*)$", line)
        if m and m.group(1) in (*REQUIRED, "Tool / service", "Impact", "Evidence", "See also"):
            fields.setdefault(m.group(1), m.group(2).strip())
    return fields


ENTRIES = _entries()
IDS = [f"{name}:{fl}" for name, fl, _ in ENTRIES]
LIVE = [(n, fl, b) for n, fl, b in ENTRIES if not POINTER.match(b)]


def test_the_log_files_have_entries_and_the_parser_finds_the_live_ones():
    assert len(ENTRIES) >= 25 and len(LIVE) >= 18, (len(ENTRIES), len(LIVE))
    assert {fl for _, fl, _ in LIVE} >= {"FL-001", "FL-011", "FL-014", "FL-024", "FL-005", "FL-025"}


@pytest.mark.parametrize(("name", "fl", "body"), LIVE, ids=[f"{n}:{f}" for n, f, _ in LIVE])
def test_a_live_entry_has_every_official_field_and_a_real_severity(name, fl, body):
    fields = _fields(body)
    missing = [f for f in REQUIRED if not fields.get(f)]
    assert not missing, f"{name} {fl} is missing or has an empty: {missing}"
    assert fields["Severity"] in SEVERITIES, (
        f"{name} {fl}: severity must be exactly High, Medium or Low, got {fields['Severity']!r}"
    )


@pytest.mark.parametrize(("name", "fl", "body"), [e for e in ENTRIES if POINTER.match(e[2])], ids=lambda v: str(v)[:20])
def test_a_pointer_entry_is_one_line_and_names_no_field(name, fl, body):
    assert len(body.splitlines()) == 1, f"{name} {fl}: a pointer entry is a single line"
    assert not _fields(body)


def test_every_fl_number_appears_once_per_file_and_a_moved_number_has_its_live_entry():
    for name in FILES:
        ids = [fl for n, fl, _ in ENTRIES if n == name]
        assert len(ids) == len(set(ids)), (name, [i for i in ids if ids.count(i) > 1])
    live_ids = {fl for _, fl, _ in LIVE}
    for _, fl, body in ENTRIES:
        if body.startswith("Moved to"):
            assert fl in live_ids, f"{fl} says it moved but no live entry exists"


def test_the_template_in_the_log_names_the_same_fields():
    template = (
        (ROOT / "FRICTION_LOG.md").read_text(encoding="utf-8").split("## Entry template")[1].split("## Entries")[0]
    )
    for field in REQUIRED:
        assert f"{field}:" in template, field
