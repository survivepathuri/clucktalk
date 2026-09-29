"""Triage rules (clucktalk.domain.triage): the deterministic floor, the strict reply validator, and combining
the two so the model can raise urgency but never lower it (docs/DESIGN.md §7 rule 3, §18)."""

from __future__ import annotations

import pytest

from clucktalk.domain.triage import (
    CHECK_TEXT,
    NOTIFIABLE_PROTOCOL,
    SIGN_TEXT,
    Category,
    Check,
    Confidence,
    Decision,
    Floor,
    InvalidDecision,
    Sign,
    Urgency,
    combine,
    floor_urgency,
    rules_decision,
    validate_decision,
)

S = Sign


def signs(*s: Sign) -> frozenset[Sign]:
    return frozenset(s)


@pytest.mark.parametrize(
    ("given", "spike", "expected"),
    [
        (signs(), False, Urgency.ROUTINE),
        (signs(S.COUGHING), False, Urgency.WATCH),
        (signs(S.COUGHING), True, Urgency.URGENT),  # record-book spike alone makes it a vet-today case
        (signs(S.SUDDEN_DEATHS), False, Urgency.URGENT),
        (signs(S.TWISTED_NECK), False, Urgency.URGENT),  # red flag without deaths
        (signs(S.SWOLLEN_HEAD, S.SUDDEN_DEATHS), False, Urgency.NOTIFIABLE_SUSPECT),
        (signs(S.DISCOLOURED_COMB), True, Urgency.NOTIFIABLE_SUSPECT),  # red flag + record-book spike
        (signs(S.PARALYSIS, S.COUGHING), True, Urgency.NOTIFIABLE_SUSPECT),
    ],
)
def test_floor(given, spike, expected):
    assert floor_urgency(given, spike).urgency is expected


def test_floor_reasons_name_their_trigger():
    assert floor_urgency(signs(S.SWOLLEN_HEAD), True).reasons == ("red_flag_sign", "mortality_spike")
    assert floor_urgency(signs(S.SUDDEN_DEATHS), False).reasons == ("sudden_deaths_reported",)


def _raw(urgency="watch", cw=None, checks=None):
    return {"urgency": urgency, "consistent_with": cw or [], "checks": checks or []}


def test_valid_reply_parses_and_dedupes():
    d = validate_decision(
        _raw(
            "urgent",
            [{"category": "respiratory", "confidence": "high"}, {"category": "respiratory", "confidence": "low"}],
            ["check_water", "check_water", "isolate_sick_birds"],
        )
    )
    assert d == Decision(Urgency.URGENT, ((Category.RESPIRATORY, Confidence.HIGH),), (Check.WATER, Check.ISOLATE))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "urgent",
        {"urgency": "urgent"},  # missing keys
        {**_raw(), "note": "give 5 ml enrofloxacin"},  # any free-text field rejects the reply
        _raw("fine"),
        _raw(cw=[{"category": "avian_influenza", "confidence": "high"}]),  # a disease name is not a category
        _raw(cw=[{"category": "respiratory", "confidence": "sure"}]),
        _raw(cw=[{"category": "respiratory", "confidence": "high", "why": "x"}]),
        _raw(checks=["give_antibiotic"]),  # a treatment is never a check
        _raw(checks=["check_water"] * 6),
        _raw(cw=[{"category": c.value, "confidence": "low"} for c in Category][:4]),
    ],
)
def test_invalid_replies_are_rejected_whole(raw):
    with pytest.raises(InvalidDecision):
        validate_decision(raw)


def test_model_can_raise_but_never_lower():
    floor = Floor(Urgency.URGENT, ("mortality_spike",))
    lowered = combine(floor, Decision(Urgency.ROUTINE, ((Category.DIGESTIVE, Confidence.LOW),), (Check.WATER,)))
    assert lowered.urgency is Urgency.URGENT
    assert lowered.checks[0] is Check.CALL_VET  # urgent always includes the vet
    raised = combine(Floor(Urgency.WATCH, ()), Decision(Urgency.URGENT, (), ()))
    assert raised.urgency is Urgency.URGENT


def test_notifiable_names_no_category_and_uses_no_model_checks():
    d = combine(
        Floor(Urgency.NOTIFIABLE_SUSPECT, ("red_flag_sign",)),
        Decision(Urgency.WATCH, ((Category.RESPIRATORY, Confidence.HIGH),), (Check.WATER,)),
    )
    assert d == Decision(Urgency.NOTIFIABLE_SUSPECT, (), ())


def test_no_decision_means_floor_only():
    assert combine(Floor(Urgency.URGENT, ()), None) == Decision(Urgency.URGENT, (), (Check.CALL_VET,))
    assert combine(Floor(Urgency.WATCH, ()), None) == Decision(Urgency.WATCH, (), ())


def test_demo_rules_reply_is_schema_valid_and_respects_the_floor():
    for given, spike in [(signs(S.COUGHING, S.SNEEZING), True), (signs(S.PANTING), False), (signs(S.LAME), False)]:
        d = validate_decision(rules_decision(given, spike))
        assert d.urgency >= floor_urgency(given, spike).urgency
    d = validate_decision(rules_decision(signs(S.COUGHING, S.SNEEZING), True))
    assert d.consistent_with == ((Category.RESPIRATORY, Confidence.MEDIUM),)
    assert d.checks[0] is Check.REMOVE_DEAD


def test_every_code_has_bilingual_text_and_no_treatment_words():
    assert set(SIGN_TEXT) == set(Sign)
    assert {c.value for c in Check} | set(NOTIFIABLE_PROTOCOL) <= set(CHECK_TEXT)
    banned = ("antibiotic", "medicine", "dose", " ml", " mg", "drug", "vaccine")
    for text in [*SIGN_TEXT.values(), *CHECK_TEXT.values()]:
        assert text.en and text.te
        assert not any(b in text.en.lower() for b in banned), text.en
