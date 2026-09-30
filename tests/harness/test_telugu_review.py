"""docs/TELUGU_REVIEW.md must list every Telugu string currently in the code with its review status, so the
native-speaker review never works from a stale copy, and any new or changed string is pending until reviewed.
Regenerate with: <venv python> scripts/telugu_review.py"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import telugu_review  # noqa: E402


def test_review_file_is_up_to_date():
    assert telugu_review.main(["--check"]) == 0


def test_every_telugu_string_has_an_english_pair():
    text = telugu_review.render()
    assert "no English pair found" not in text
    assert text.count("| `src/") >= 60  # guards against the extractor silently finding nothing


def test_changing_either_language_makes_a_string_pending():
    en, te = "Feed stock lasts about {days} days.", "ఫీడ్ నిల్వ సుమారు {days} రోజులు సరిపోతుంది."
    approved = {telugu_review.string_key(en, te): {"reviewer": "R", "date": "2026-09-27"}}
    rows = [
        {"en": en, "te": te},  # unchanged: approved
        {"en": en, "te": te + " "},  # Telugu changed
        {"en": en + "!", "te": te},  # English changed: the translation must be re-checked
        {"en": None, "te": "కొత్త"},  # new string
    ]
    for r in rows:
        r["key"] = telugu_review.string_key(r["en"], r["te"])
    pending, ok = telugu_review.split_by_status(rows, approved)
    assert ok == rows[:1] and pending == rows[1:]


def test_pending_strings_are_listed_first_and_the_gate_fails(monkeypatch, capsys):
    monkeypatch.setattr(telugu_review, "load_approvals", lambda path=None: {})
    text = telugu_review.render({})
    assert text.index("## 1. Pending review") < text.index("## 2. Approved (0)")
    assert "Nothing pending." not in text
    assert telugu_review.main(["--require-none-pending"]) == 1


def test_approvals_file_is_well_formed():
    data = json.loads(telugu_review.APPROVALS.read_text(encoding="utf-8"))
    keys = [a["key"] for a in data["approvals"]]
    assert len(keys) == len(set(keys))
    for a in data["approvals"]:
        assert a["key"] == telugu_review.string_key(a["en"], a["te"])
        assert a["reviewer"].strip()
        date.fromisoformat(a["date"])
