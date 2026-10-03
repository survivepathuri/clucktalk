"""Review finding M6, stage 1 (Step 47C): the structured `safety` field of the briefing and the farm status comes from
ONE shared helper, maps the card's own level word and so can never be lower than the existing rules, and has a stable
schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clucktalk.server.tools.safety import SAFETY_LEVELS, SafetyOut, safety_from

CARD_TO_SAFETY = {"ok": "OK", "info": "OK", "none": "OK", "watch": "WATCH", "alert": "ALERT", "unknown": "UNKNOWN"}


@pytest.mark.parametrize(("card", "expected"), list(CARD_TO_SAFETY.items()))
def test_the_level_is_the_cards_own_level_word(card, expected):
    assert safety_from(card, [], False).level == expected


def test_an_unknown_card_level_word_is_refused_loudly():
    with pytest.raises(KeyError):
        safety_from("fine", [], False)


def test_the_four_levels_are_the_whole_vocabulary():
    assert SAFETY_LEVELS == ("OK", "WATCH", "ALERT", "UNKNOWN")


def test_reason_codes_are_unique_and_keep_the_order_first_seen():
    s = safety_from("alert", ["open_health_check", "mortality_spike", "open_health_check", "urgent"], True)
    assert s.reason_codes == ["open_health_check", "mortality_spike", "urgent"]
    assert s.vet_contact_advised is True


def test_the_schema_is_stable_three_required_fields_and_nothing_else():
    schema = SafetyOut.model_json_schema()
    assert list(schema["properties"]) == ["level", "reason_codes", "vet_contact_advised"]
    assert set(schema["required"]) == {"level", "reason_codes", "vet_contact_advised"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["level"]["enum"] == ["OK", "WATCH", "ALERT", "UNKNOWN"]


def test_an_extra_or_bad_field_is_refused():
    with pytest.raises(ValidationError):
        SafetyOut(level="ALERT", reason_codes=[], vet_contact_advised=False, note="x")
    with pytest.raises(ValidationError):
        SafetyOut(level="HIGH", reason_codes=[], vet_contact_advised=False)


def test_reason_codes_are_codes_never_sentences():
    s = safety_from("watch", ["feed_intake_drop"], False)
    assert all(c.replace("_", "").isalnum() and c == c.lower() for c in s.reason_codes)


# -- the builders, with plain item objects (the whole-farm briefing always has other sheds' items in it) -------------
from types import SimpleNamespace as NS  # noqa: E402

from clucktalk.server.tools.safety import briefing_safety, status_safety  # noqa: E402


def _item(category, level, **values):
    return NS(category=category, level=level, values=values)


def test_an_escalated_watch_follow_up_advises_the_vet_in_the_briefing_but_a_due_one_does_not():
    never = lambda item: False  # noqa: E731  (the briefing's own closing-step rule says no)
    escalated = briefing_safety("alert", [_item("follow_up", "alert", urgency="watch", state="escalated")], never)
    due = briefing_safety("watch", [_item("follow_up", "watch", urgency="watch", state="due")], never)
    assert escalated.vet_contact_advised is True and due.vet_contact_advised is False
    assert escalated.reason_codes == ["follow_up", "watch", "escalated"]


def test_the_briefing_safety_step_rule_is_used_as_given():
    yes = briefing_safety("alert", [_item("mortality_spike", "alert")], lambda item: True)
    no = briefing_safety("alert", [_item("mortality_spike", "alert")], lambda item: False)
    assert yes.vet_contact_advised is True and no.vet_contact_advised is False


def test_items_below_watch_give_no_reason_codes():
    s = briefing_safety("info", [_item("sale_window", "info")], lambda item: False)
    assert s.level == "OK" and s.reason_codes == []


def test_the_status_builder_marks_not_checked_and_no_house_checked():
    # the status builder now reads the facts (the unavailable shed is a not_checked fact), like the briefing
    s = status_safety("unknown", [_item("not_checked", "watch")], lambda item: False)
    assert s.level == "UNKNOWN" and s.reason_codes == ["not_checked", "no_house_checked"]


# -- Step 48C part A: one rule, one gathering, for both tools -------------------------------------------------------
from clucktalk.server.tools.safety import item_needs_safety_step  # noqa: E402


def _fact(category, level, pinned=True, **values):
    return NS(category=category, level=level, pinned=pinned, values=values)


@pytest.mark.parametrize("category", ["mortality_spike", "recent_logged_spike", "cum_mortality_high"])
def test_a_pinned_death_fact_needs_the_vet_step_and_an_unpinned_one_does_not(category):
    assert item_needs_safety_step(_fact(category, "alert")) is True
    assert item_needs_safety_step(_fact(category, "alert", pinned=False)) is False


@pytest.mark.parametrize(("urgency", "expected"), [("watch", False), ("routine", False), ("urgent", True)])
def test_a_health_check_needs_the_vet_step_only_when_urgent_or_reportable(urgency, expected):
    assert item_needs_safety_step(_fact("open_health_check", "alert", urgency=urgency)) is expected
    assert item_needs_safety_step(_fact("follow_up", "alert", urgency=urgency)) is expected
    assert item_needs_safety_step(_fact("open_health_check", "alert", urgency="notifiable_suspect")) is True


def test_the_status_and_the_briefing_builders_give_the_same_answer_for_the_same_items():
    items = [_fact("mortality_spike", "alert"), _fact("feed_stock_low", "watch", pinned=False)]
    a = briefing_safety("alert", items, item_needs_safety_step)
    b = status_safety("alert", items, item_needs_safety_step)
    assert a == b and a.vet_contact_advised is True and a.reason_codes == ["mortality_spike", "feed_stock_low"]


def test_the_level_is_raised_to_the_facts_when_the_card_is_lower_and_never_lowered():
    items = [_fact("recent_logged_spike", "alert")]
    assert status_safety("ok", items, item_needs_safety_step).level == "ALERT"
    assert status_safety("alert", [], item_needs_safety_step).level == "ALERT"
    assert (
        status_safety("ok", [_fact("feed_stock_low", "watch", pinned=False)], item_needs_safety_step).level == "WATCH"
    )
    assert (
        status_safety("unknown", [_fact("not_checked", "watch", pinned=False)], item_needs_safety_step).level
        == "UNKNOWN"
    )


def test_a_simulated_item_is_a_reason_code_only_when_nothing_else_explains_the_level():
    sale = NS(category="sale_window", level="watch", pinned=False, values={}, simulated=True)
    spike = _fact("mortality_spike", "alert")
    both = status_safety("alert", [spike, sale], item_needs_safety_step)
    assert both.reason_codes == ["mortality_spike"]
    alone = status_safety("watch", [sale], item_needs_safety_step)
    assert alone.reason_codes == ["sale_window"] and alone.level == "WATCH" and alone.vet_contact_advised is False
