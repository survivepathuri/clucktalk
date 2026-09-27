"""docs/TELUGU_REVIEW.md must list every Telugu string currently in the code, so the native-speaker review
never works from a stale copy. Regenerate with: .venv/Scripts/python scripts/telugu_review.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import telugu_review  # noqa: E402


def test_review_file_is_up_to_date():
    assert telugu_review.main(["--check"]) == 0


def test_every_telugu_string_has_an_english_pair():
    text = telugu_review.render()
    assert "no English pair found" not in text
    assert text.count("| `src/") >= 60  # guards against the extractor silently finding nothing
