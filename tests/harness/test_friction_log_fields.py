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


# -- Step 49b part C: FL-026, FR-008, the counts and the Devpost copies -----------------------------------------------
def _fl_numbers(text: str, pattern: str) -> list[str]:
    return re.findall(pattern, text)


def test_the_header_counts_equal_the_entries_found():
    log = (ROOT / "FRICTION_LOG.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*Counts:\*\* (\d+) FL numbers .*?: (\d+) live entries \((\d+) in this file, (\d+) in", log)
    assert m, "the log header states the counts"
    numbers, live, here, dev = (int(x) for x in m.groups())
    found = [fl for _, fl, _ in ENTRIES]
    assert numbers == len(set(found)) == 26
    assert live == len(LIVE) == here + dev
    assert here == len([1 for n, _, _ in LIVE if n == "FRICTION_LOG.md"]) and dev == len(
        [1 for n, _, _ in LIVE if n == "docs/DEV_NOTES.md"]
    )


def test_fl_026_is_a_low_severity_alexa_docs_entry_that_says_what_it_does_not_show():
    body = next(b for _, fl, b in LIVE if fl == "FL-026")
    fields = _fields(body)
    assert fields["Severity"] == "Low" and fields["Tag"] == "[Alexa+/MCP]" and fields["Date"] == "2026-10-04"
    assert "2025-06-18" in fields["Expected vs actual"] and "addon-local-inspector" in fields["Expected vs actual"]
    assert "2025-11-25" in fields["Expected vs actual"] and "no minimum protocolVersion" in fields["Expected vs actual"]
    assert "neither shows Amazon's behavior" in fields["Workaround"]
    assert fields["Time cost"] == "not recorded" and fields["Reproduce"].startswith("documentation-based, no command")
    assert "Alexa+ MCP Toolkit documentation team" in fields["Actionable suggestion"]
    for path in re.findall(r"`([^`]+\.(?:md|py))`", fields["Evidence"]):
        assert (ROOT / path.split(" ")[0]).exists(), path


def test_fr_008_is_a_nice_to_have_question_tied_to_fl_026():
    text = (ROOT / "FEATURE_REQUESTS.md").read_text(encoding="utf-8")
    block = text.split("### FR-008:")[1].split("\n### ")[0]
    assert "Priority: Nice-to-have" in block and "Related friction-log entry: FL-026" in block
    assert "distributionCountries" in block and "a question, not a claim" in block and "IN" in block
    assert "Alexa+ MCP Toolkit documentation team" in block


PASTES = ("docs/DEVPOST_FRICTION_PASTE.md", "docs/DEVPOST_FRICTION_PASTE_SHORT.md")


@pytest.mark.parametrize("name", PASTES)
def test_each_devpost_copy_has_every_live_non_dev_entry_once_in_numbered_order(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    headings = re.findall(r"(?m)^## Entry (\d+) \((FL-\d{3})\)", text)
    assert [int(n) for n, _ in headings] == list(range(1, len(headings) + 1))
    expected = {fl for n, fl, _ in LIVE if n == "FRICTION_LOG.md"}
    assert sorted(fl for _, fl in headings) == sorted(expected)


@pytest.mark.parametrize("name", PASTES)
def test_fl_026_is_entry_10_right_after_fl_020_and_the_priority_five_stay_on_top(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    order = [fl for _, fl in re.findall(r"(?m)^## Entry (\d+) \((FL-\d{3})\)", text)]
    assert order[:5] == ["FL-014", "FL-024", "FL-009", "FL-017", "FL-013"]
    assert order[order.index("FL-020") + 1] == "FL-026" and order.index("FL-026") == 9


def test_every_short_entry_is_under_120_words():
    text = (ROOT / PASTES[1]).read_text(encoding="utf-8")
    entries = re.split(r"(?m)^## Entry ", text)[1:]
    assert len(entries) >= 19
    for entry in entries:
        assert len(entry.split()) < 120, entry.splitlines()[0]


def test_fl_026_agrees_across_the_log_and_both_copies():
    log = next(b for _, fl, b in LIVE if fl == "FL-026")
    for name in PASTES:
        text = (ROOT / name).read_text(encoding="utf-8")
        entry = text.split("(FL-026)")[1].split("\n## Entry ")[0]
        assert "Severity:** Low" in entry and "[Alexa+/MCP]" in entry and "Origin:** Amazon" in entry
        assert "2025-06-18" in entry and "2025-11-25" in entry
    assert "Severity: Low" in log
