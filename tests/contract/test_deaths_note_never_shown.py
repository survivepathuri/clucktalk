"""The death-limit file's ``note`` is for whoever keeps the file, never for the farmer.

It must not appear in any farmer-visible text (English or Telugu), spoken or structured, for either kind of rule, in the
pilot or the demo, on the status or the briefing. The rule itself (levels, the vet line, the numbers) is untouched."""

from __future__ import annotations

import json

import pytest

from clucktalk.domain.daily_deaths import AgeBand, DailyDeathsRule
from tests.contract import test_daily_deaths_display as per_1000
from tests.contract import test_daily_limit_display as banded

BUILDER_NOTE = "farmer-declared limits for a 4000-bird shed, relayed by the builder; written confirmation is pending"
BANDS = (AgeBand(0, 29, 6), AgeBand(30, None, 3))


def everything_the_farmer_can_see(outputs) -> str:
    """Every field of every answer, as one text: the spoken and written text, the findings, the structured fields."""
    return json.dumps(outputs, ensure_ascii=False)


@pytest.mark.parametrize("example", [False, True])
def test_the_per_1000_rule_note_is_never_shown(example):
    source = per_1000.make_source()
    source.deaths_rule = per_1000.Fixed(DailyDeathsRule(per_1000.RULE.per_1000_live, BUILDER_NOTE, example))
    on, whole, brief = per_1000.asked(source)
    assert per_1000.codes(on) == ["daily_deaths_rule"]  # the rule still fires: only the note is gone
    seen = everything_the_farmer_can_see([on, whole, brief])
    for fragment in (BUILDER_NOTE, "relayed by the builder", "Your note", "మీ గమనిక"):
        assert fragment not in seen, fragment


@pytest.mark.parametrize("example", [False, True])
def test_the_age_limit_note_is_never_shown_and_the_vet_line_stays(tmp_path, example):
    source = banded.make_source(tmp_path, 20, 7)
    source.deaths_rule = banded.Fixed(DailyDeathsRule(None, BUILDER_NOTE, example, BANDS))
    on, whole, brief = banded.asked(source)
    assert banded.codes(on) == ["daily_limit_exceeded"] and on["level"] == "alert"
    assert banded.VET in on["text_en"] and "take the birds to the vet today" in on["text_en"]
    seen = everything_the_farmer_can_see([on, whole, brief])
    for fragment in (BUILDER_NOTE, "relayed by the builder", "Your note", "మీ గమనిక"):
        assert fragment not in seen, fragment


def test_without_a_note_the_answer_is_what_it_was_and_the_unreadable_line_still_shows(tmp_path):
    source = banded.make_source(tmp_path, 20, 7)
    source.deaths_rule = banded.Fixed(DailyDeathsRule(None, None, False, BANDS))
    plain = banded.asked(source)[0]["text_en"]
    source.deaths_rule = banded.Fixed(DailyDeathsRule(None, BUILDER_NOTE, False, BANDS))
    assert banded.asked(source)[0]["text_en"] == plain  # a note changes nothing the farmer reads
    source.deaths_rule = banded.Fixed(None, unreadable=True)
    assert "I couldn't read your own daily deaths rule, so it was not used." in banded.asked(source)[0]["text_en"]
