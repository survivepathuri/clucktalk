"""Step 50W-B part D: the README section "Weather reminders" says in plain words what the feature is and is not, how to
run the demo, the free-tier limit and that it is off unless the rules file exists; the claims table has its rows; the
design document has its note."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify  # noqa: E402

README = (ROOT / "README.md").read_text(encoding="utf-8")
FLAT = " ".join(README.split())
SECTION = " ".join(README.split("## Weather reminders")[1].split("\n## ")[0].split())
DESIGN = " ".join((ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8").split())


def test_the_section_exists_before_the_demo_clock_and_after_the_voice_versus_cards_section():
    assert "## Weather reminders" in README
    assert README.index("## Voice versus cards") < README.index("## Weather reminders") < README.index("## Demo clock")


def test_it_says_what_it_is():
    for needle in (
        "your own outdoor-temperature rules",
        "hourly outdoor forecast",
        "one reminder line per rule",
        "the lowest or the highest forecast temperature",
        "the number you set",
        "your own note",
        "docs/weather_rules.example.json",
        "two example rules",
        "never used unless you point at the file",
    ):
        assert needle in SECTION, needle


def test_it_says_what_it_is_not():
    for needle in (
        "It gives no advice",
        "not a temperature inside the shed",
        "20 to 30",
        "is not stored or compared with anything",
        "not real-time",
        "no push",
        "set in a config file",
        "entering them by voice is a roadmap item",
        "never changes a shed's health status, safety level, reason codes, vet advice or any card level",
    ):
        assert needle in SECTION, needle


def test_it_is_off_unless_the_file_exists_and_says_so_with_the_test_that_shows_it():
    assert "off unless the rules file exists" in SECTION
    assert "nothing is asked of any weather service" in SECTION
    assert "byte-identical" in SECTION and "tests/contract/test_weather_display.py" in SECTION


def test_it_gives_the_demo_command_and_the_example_settings_label():
    assert "CLUCKTALK_WEATHER_RULES_PATH=docs\\weather_rules.example.json" in README.split("## Weather reminders")[1]
    assert "python tasks.py serve" in README.split("## Weather reminders")[1].split("## Demo clock")[0]
    assert "labelled Demo data and Simulated" in SECTION
    assert "example settings" in SECTION and "12 hours" in SECTION


def test_it_states_the_free_tier_limit_the_source_the_attribution_and_what_was_not_run():
    for needle in (
        "Open-Meteo",
        "non-commercial",
        "CLUCKTALK_WEATHER_LIVE=true",
        "no API key",
        "tested only with a fake transport",
        "has not been run against the real service",
        "CC-BY 4.0",
        "docs/SOURCES.md",
    ):
        assert needle in SECTION, needle


def test_it_lists_the_open_questions_for_the_farmer_without_guessing():
    for needle in ("below 20", "night minimum", "how many hours ahead", "time of day", "inside the shed or outside"):
        assert needle in SECTION.lower(), needle
    assert "relayed by the builder and not yet confirmed by the farmer" in SECTION


def test_the_claims_table_has_the_weather_rows_and_their_evidence_exists():
    rows = [ln for ln in README.splitlines() if ln.startswith("|") and "eather" in ln and "---" not in ln]
    assert len(rows) >= 3
    statuses = {r.strip("|").split("|")[1].strip().split(" ")[0] for r in rows}
    assert {"VERIFIED", "SIMULATED", "UNVERIFIED"} <= statuses
    for row in rows:
        for ref in re.findall(r"`([^`]+)`", row.split("|")[3] if row.count("|") >= 4 else ""):
            if ref.startswith("python tasks.py"):
                continue
            assert (ROOT / ref.split("::")[0].split(" ")[0]).exists(), ref


def test_the_design_document_has_the_note_with_the_limits_that_held():
    assert "Weather reminders (Step 50W-B)" in DESIGN
    note = DESIGN.split("Weather reminders (Step 50W-B)")[1][:2500]
    for needle in ("no new MCP tool", "no schema change", "no card", "weather_reminders", "feeds nothing", "SIMULATED"):
        assert needle in note, needle


def test_the_forbidden_claims_scan_still_finds_nothing_in_the_new_text():
    assert verify.scan_files() == []
