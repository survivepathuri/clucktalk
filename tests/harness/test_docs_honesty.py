"""Docs that must stay honest (Session 5 review, section E): the eval count equals the real table, the roadmap does not
list built features as future work, DESIGN section 18 says where the follow-up shows, and the claim "the card sentence
equals the spoken sentence" is limited to the Simulator in the README, DESIGN and the skill."""

from __future__ import annotations

import json
import re

from clucktalk.config import REPO_ROOT

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
DESIGN = (REPO_ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")
EVALS = (REPO_ROOT / "docs" / "EVALS.md").read_text(encoding="utf-8")
SKILL = REPO_ROOT / "skills" / "clucktalk"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = re.search(r"^## ", text[start + len(heading) :], re.M)
    return text[start : start + len(heading) + (nxt.start() if nxt else len(text))]


def test_the_design_eval_count_equals_the_evals_table_and_the_golden_file():
    rows = re.findall(r"^\| [\w-]+ \| (?:PASS|FAIL) \|", EVALS, re.M)
    cases = json.loads((REPO_ROOT / "data" / "eval" / "golden_cases.json").read_text(encoding="utf-8"))["cases"]
    (stated,) = re.findall(r"The suite has (\d+) cases", DESIGN)
    assert int(stated) == len(rows) == len(cases), (stated, len(rows), len(cases))


def test_the_readme_roadmap_does_not_list_built_features_as_future_work():
    roadmap = _section(README, "## Roadmap").lower()
    for built in ("record book", "health triage"):
        if built in roadmap:  # only to say it is built
            assert "are built" in roadmap, built
    today = _section(README, "## What it does today").lower()
    for built in ("record book", "triage", "follow-up"):
        assert built in today, built


def test_the_design_says_the_follow_up_shows_on_the_briefing_and_farm_status_cards():
    section = DESIGN[DESIGN.index("- **Flock Follow-up**") :]
    assert "no card shows it yet" not in section
    assert "the briefing and the\n  farm status, and their cards" in section or "and their cards" in section


def test_the_card_equals_spoken_claim_is_limited_to_the_simulator_everywhere():
    assert "Simulator only" in README and "composes\nits own speech" in README.replace("\r\n", "\n")
    assert "On Alexa+" in DESIGN and "composes its own speech" in DESIGN
    for name in ("SKILL.md", "references/voice-and-cards.md", "references/safety-rules.md"):
        text = (SKILL / name).read_text(encoding="utf-8")
        assert "words its own answer" in text, name


def test_the_skill_promises_no_wording_the_server_cannot_guarantee():
    for path in SKILL.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "word for word" not in text, path.name
        assert "all end with" not in text, path.name


def test_the_skill_says_four_cards_serve_five_tools():
    text = (SKILL / "references" / "voice-and-cards.md").read_text(encoding="utf-8")
    assert "Four cards serve five tools" in text
    assert "Five tools have one" not in text and "four tools have a card" not in text.lower()


# -- Step 47B part B: the demo clock's honest scope ------------------------------------------------------------------
def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_demo_clock_scope_is_stated_in_the_readme_design_and_skill():
    skill = (SKILL / "references" / "voice-and-cards.md").read_text(encoding="utf-8")
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for name, text in (("README", README), ("DESIGN", DESIGN), ("skill", skill), ("SKILL.md", skill_md)):
        flat = _flat(text).lower()
        assert "follow-up and briefing dates only" in flat, name
        assert "flock ages" in flat and "record-book entries" in flat and "sale plan do not move" in flat, name
        assert "time passing for the flock" in flat, name


def test_the_demo_clock_uses_its_own_state_file_and_reset_demo_clears_both():
    for name, text in (("README", README), ("DESIGN", DESIGN)):
        flat = _flat(text)
        assert "separate state file" in flat and "never the live" in flat, name
    assert "reset-demo` clears both files" in _flat(README)


def test_the_demo_clock_file_has_one_name_in_code_readme_and_design():
    from clucktalk.config import DEFAULT_STATE_PATH, DEMO_CLOCK_STATE_SUFFIX, load_settings

    name = load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_DEMO_DAYS_LATER": "3"}).demo_clock_state_path.name
    assert name == f"{DEFAULT_STATE_PATH.stem}{DEMO_CLOCK_STATE_SUFFIX}.sqlite3" == "clucktalk_demo_clock.sqlite3"
    assert f".local/{name}" in README and f".local/{name}" in DESIGN
