"""Step 51 part B: the farmer's daily deaths rule on the farm status and the briefing.

It can only RAISE a shed to WATCH. It never lowers a level, never changes the vet advice, and the existing health and
safety text always comes first, then his note. With no rule file every answer is byte-identical to what it was."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from clucktalk.agents import demo_ai
from clucktalk.agents.briefing import BriefingRanker
from clucktalk.domain.daily_deaths import DailyDeathsRule
from clucktalk.domain.models import DailyRecord
from clucktalk.domain.triage import Urgency
from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.daily_deaths import DeathsRuleFile, RuleState
from clucktalk.server.farm_state import IST, PilotFarmSource
from clucktalk.server.tools.briefing import build_briefing
from clucktalk.server.tools.farm_status import build_status

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)
NOTE = "check the water and the shed today"
RULE = DailyDeathsRule(Decimal("2"), NOTE, False)


class Fixed:
    """A rule source for tests: the same ``current()`` the real file object has."""

    def __init__(self, rule=None, unreadable=False):
        self.state = RuleState(rule, unreadable)

    def current(self):
        return self.state


def make_source(today_deaths=9, earlier=4, days=6):
    """Shed 1: 3000 birds, ``earlier`` deaths a day for the days before today, ``today_deaths`` today. With 4 a day
    for 6 days there are 2976 live birds at the start of today; 9 deaths is 3.02 per 1000 (more than 2: the rule fires)
    but is NOT a spike (3 x 4 = 12)."""
    source = PilotFarmSource(
        load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json"), clock=lambda: TODAY, now=lambda: NOW
    )
    farm_id = source.farm_id
    for i in range(days, 0, -1):
        source.store.put_record(farm_id, "house-1", DailyRecord(TODAY - timedelta(days=i), earlier, 100.0))
    source.store.put_record(farm_id, "house-1", DailyRecord(TODAY, today_deaths, 100.0))
    return source


def asked(source):
    ranker = BriefingRanker(source.store, demo_ai(), source.now)
    return (
        build_status(source, "shed one").model_dump(mode="json"),
        build_status(source, None).model_dump(mode="json"),
        build_briefing(source, ranker).model_dump(mode="json"),
    )


def codes(shed):
    return [f["code"] for f in shed["houses"][0]["findings"] if f["code"] != "no_reference_curve"]


def test_a_shed_that_is_otherwise_fine_becomes_watch_with_the_rule_and_says_why():
    source = make_source()
    off, _, brief_off = asked(source)
    # (shed 2 has no records yet, so the whole-farm answers are WATCH for that reason; shed 1 alone is the clean case)
    assert off["level"] == "ok" and codes(off) == []
    assert all(i["category"] != "daily_deaths_rule" for i in brief_off["items"])
    source.deaths_rule = Fixed(RULE)
    on, whole, brief = asked(source)
    assert on["level"] == "watch"
    assert any(f["code"] == "daily_deaths_rule" for h in whole["houses"] for f in h["findings"])
    finding = on["houses"][0]["findings"][0]
    assert finding["code"] == "daily_deaths_rule" and finding["level"] == "watch"
    assert finding["values"] == {"deaths": 9.0, "live_at_start": 2976.0, "per_1000": 3.02, "limit_per_1000": 2.0}
    assert "9 birds died today, that is 3.02 for every 1000 birds, more than your own limit of 2." in on["text_en"]
    assert "చనిపోయాయి" in on["text_te"] and "3.02" in on["text_te"]
    item = next(i for i in brief["items"] if i["category"] == "daily_deaths_rule")
    assert item["level"] == "watch" and item["pinned"] is True and item["text_en"].startswith("House 1:")
    assert on["safety"] == {"level": "WATCH", "reason_codes": ["daily_deaths_rule"], "vet_contact_advised": False}
    assert "daily_deaths_rule" in brief["safety"]["reason_codes"] and brief["safety"]["vet_contact_advised"] is False
    assert on["safety"]["reason_codes"] == ["daily_deaths_rule"]


def test_his_note_is_never_part_of_an_answer():
    # Changed on purpose (Commit A): the note is for whoever keeps the file, not for the farmer (the full check is in
    # test_deaths_note_never_shown.py). Before, it came last in every answer.
    source = make_source()
    source.deaths_rule = Fixed(RULE)
    on, _, brief = asked(source)
    for answer in (on, brief):
        assert NOTE not in answer["text_en"] and NOTE not in answer["text_te"]
        assert "Your note" not in answer["text_en"] and "మీ గమనిక" not in answer["text_te"]
    assert "more than your own limit of 2." in on["text_en"]  # the rule's own factual line is still there


def test_exactly_his_number_changes_nothing_and_one_more_death_fires():
    # No earlier days (so no spike baseline) and 3000 live birds at the start: 6 deaths is exactly 2 per 1000.
    source = make_source(today_deaths=6, earlier=0, days=0)
    source.deaths_rule = Fixed(RULE)
    off, _, _ = asked(source)
    assert codes(off) == [] and off["level"] == "ok" and "Your note" not in off["text_en"]
    source = make_source(today_deaths=7, earlier=0, days=0)
    source.deaths_rule = Fixed(RULE)
    assert codes(asked(source)[0]) == ["daily_deaths_rule"]


def test_it_never_lowers_an_alert_and_the_vet_advice_stays_the_same():
    source = make_source(today_deaths=40, earlier=4)  # a real spike: ALERT from the existing rules
    base_status, _, base_brief = asked(source)
    assert base_status["level"] == "alert"
    source.deaths_rule = Fixed(RULE)
    on, _, brief = asked(source)
    assert on["level"] == "alert" and brief["level"] == "alert"
    assert on["safety"]["level"] == base_status["safety"]["level"] == "ALERT"
    assert on["safety"]["vet_contact_advised"] is True and base_status["safety"]["vet_contact_advised"] is True
    assert "Please check the birds today and call your vet if deaths continue." in on["text_en"]
    assert "Your note" not in on["text_en"] and "Your note" not in brief["text_en"]  # (the note is never shown)
    assert on["houses"][0]["findings"][0]["code"] == "mortality_spike"  # the alert stays first


def add_check(source, house_number, urgency):
    """A stored, answered health check of the given urgency, made now (the same rows the triage tool writes)."""
    from clucktalk.domain.triage import (
        CheckStatus,
        Floor,
        HealthCheck,
        Sign,
        TriageInput,
        TriageResult,
        new_check_id,
    )

    inp = TriageInput(
        f"house-{house_number}", f"House {house_number}", f"షెడ్ {house_number}", "flock", 40, 900, (Sign.COUGHING,),
        None, None, None, 2, 1.0, False, None, TODAY.isoformat(),
    )  # fmt: skip
    result = TriageResult(urgency, (), (), "rules", None, None)
    check = HealthCheck(
        new_check_id(),
        source.farm_id,
        f"house-{house_number}",
        NOW,
        CheckStatus.READY,
        inp,
        Floor(urgency, ()),
        result,
        NOW,
    )
    source.store.add_health_check(check)


def test_a_suspected_reportable_disease_keeps_its_text_first_and_his_note_is_not_shown():
    source = make_source()  # 9 deaths today: his rule fires on shed 1
    add_check(source, 1, Urgency.NOTIFIABLE_SUSPECT)
    off, _, off_brief = asked(source)
    source.deaths_rule = Fixed(RULE)
    on, _, on_brief = asked(source)
    assert "daily_deaths_rule" in codes(on) and on["level"] == off["level"] == "alert"  # alert stays alert
    assert on["safety"]["level"] == off["safety"]["level"] == "ALERT"
    assert on["safety"]["vet_contact_advised"] is True and off["safety"]["vet_contact_advised"] is True
    assert set(off["safety"]["reason_codes"]) <= set(on["safety"]["reason_codes"])
    line = next(f["text_en"] for f in on["houses"][0]["findings"] if f["code"] == "daily_deaths_rule")
    # Take out his one factual line: what is left is exactly what he heard without the rule (and no note).
    assert on["text_en"].replace(f" {line}", "") == off["text_en"]
    for a in (on, on_brief):
        assert NOTE not in a["text_en"] and "Your note" not in a["text_en"]
        assert a["text_en"].index("reportable disease") < a["text_en"].index("call your vet")  # the check text first
    spoken_check = off["houses"][0]["open_health_check"]
    assert spoken_check is not None and spoken_check["urgency"] == "notifiable_suspect"


def test_an_unreadable_rule_is_said_and_changes_no_level():
    source = make_source()
    off, off_whole, off_brief = asked(source)
    source.deaths_rule = Fixed(None, unreadable=True)
    on, on_whole, on_brief = asked(source)
    for a, b in ((on, off), (on_whole, off_whole), (on_brief, off_brief)):
        assert a["level"] == b["level"] and a["safety"] == b["safety"]
        assert a["text_en"].startswith(b["text_en"])
        assert a["text_en"].endswith("I couldn't read your own daily deaths rule, so it was not used.")
        assert "మీరు పెట్టిన రోజువారీ మరణాల నియమం" in a["text_te"]


def test_with_no_rule_the_answers_are_exactly_what_they_were():
    source = make_source()
    plain = asked(source)
    source.deaths_rule = None
    assert asked(source) == plain
    source.deaths_rule = Fixed(None, unreadable=False)  # a file object whose file does not exist
    assert asked(source) == plain


def test_a_real_rule_file_object_works_end_to_end(tmp_path):
    path = tmp_path / "daily_deaths_rule.json"
    path.write_text(json.dumps({"per_1000_live": 2, "note": NOTE}), encoding="utf-8")
    source = make_source()
    source.deaths_rule = DeathsRuleFile(path)
    on, _, _ = asked(source)
    assert codes(on) == ["daily_deaths_rule"] and NOTE not in on["text_en"] and "Your note" not in on["text_en"]


def test_an_example_rule_shows_no_note_and_no_demo_line_in_the_demo():
    # Changed on purpose (Commit A): the "Demo data." line only ever introduced the note, which is no longer shown.
    from clucktalk.server.farm_state import DemoFarmSource

    source = DemoFarmSource(clock=lambda: date(2026, 9, 29))
    source.deaths_rule = Fixed(DailyDeathsRule(Decimal("2"), NOTE, True))
    on = build_status(source, "shed 2").model_dump(mode="json")
    assert NOTE not in on["text_en"] and "Your note" not in on["text_en"]


@pytest.mark.parametrize("deaths", [0, 1, 4, 5])  # 5 / 2976 * 1000 = 1.68; 6 would be 2.02
def test_small_days_never_fire(deaths):
    source = make_source(today_deaths=deaths, earlier=4)
    source.deaths_rule = Fixed(RULE)
    on, _, _ = asked(source)
    assert "daily_deaths_rule" not in codes(on)


def test_a_note_with_odd_spacing_is_not_shown_either():
    source = make_source()
    source.deaths_rule = Fixed(DailyDeathsRule(Decimal("2"), "  check   the water ", False))
    on, _, brief = asked(source)
    assert "check   the water" not in on["text_en"] and "check   the water" not in brief["text_en"]
    assert "Your note" not in on["text_en"] and "Your note" not in brief["text_en"]
