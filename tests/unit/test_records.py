"""``merge_daily_record`` / ``validate_record_day`` (docs/DESIGN.md §13.4): hand-computed cases, since these are
the rules a farmer's voice correction relies on to never silently drop what was already logged."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clucktalk.domain.errors import RecordDayOutOfRange, WeightSampleNeedsBirdCount
from clucktalk.domain.models import DailyRecord, Treatment, TreatmentKind
from clucktalk.domain.records import merge_daily_record, validate_record_day
from tests.unit.helpers import D0, broiler_house, layer_house

VACCINE = Treatment(TreatmentKind.VACCINE, "Newcastle")
MEDICINE = Treatment(TreatmentKind.MEDICINE, "Amoxicillin", note="1 course")


def _merge(existing, deaths=None, feed_kg=None, avg_weight_g=None, weight_sample_birds=None, treatments=None):
    return merge_daily_record(
        existing, D0, deaths, feed_kg, avg_weight_g, weight_sample_birds, treatments, "House 1", "షెడ్ 1"
    )


def test_a_brand_new_day_with_only_deaths_given_defaults_everything_else():
    rec = _merge(None, deaths=3)
    assert rec == DailyRecord(D0, 3, 0.0)


def test_a_brand_new_day_with_only_feed_given_defaults_deaths_to_zero():
    rec = _merge(None, feed_kg=120.0)
    assert rec == DailyRecord(D0, 0, 120.0)


def test_a_correction_overwrites_only_the_field_given_and_keeps_the_rest():
    existing = DailyRecord(D0, deaths=5, feed_kg=100.0, avg_weight_g=1800.0, weight_sample_birds=10)
    corrected = _merge(existing, deaths=7)
    assert corrected == DailyRecord(D0, deaths=7, feed_kg=100.0, avg_weight_g=1800.0, weight_sample_birds=10)


def test_deaths_zero_is_a_given_value_not_a_missing_one():
    existing = DailyRecord(D0, deaths=5, feed_kg=100.0)
    corrected = _merge(existing, deaths=0)
    assert corrected.deaths == 0


def test_weight_sample_is_replaced_as_a_pair_not_merged_field_by_field():
    existing = DailyRecord(D0, deaths=0, feed_kg=100.0, avg_weight_g=1800.0, weight_sample_birds=10)
    corrected = _merge(existing, avg_weight_g=1900.0, weight_sample_birds=12)
    assert (corrected.avg_weight_g, corrected.weight_sample_birds) == (1900.0, 12)


def test_weight_without_a_bird_count_is_rejected_even_when_correcting_an_existing_sample():
    existing = DailyRecord(D0, deaths=0, feed_kg=100.0, avg_weight_g=1800.0, weight_sample_birds=10)
    with pytest.raises(WeightSampleNeedsBirdCount) as e:
        _merge(existing, avg_weight_g=1900.0)
    assert e.value.customer_message == "I have an average weight for House 1 but not how many birds were weighed."


def test_weight_without_a_bird_count_is_rejected_on_a_brand_new_day_too():
    with pytest.raises(WeightSampleNeedsBirdCount):
        _merge(None, avg_weight_g=1900.0)


def test_treatments_add_to_the_day_instead_of_replacing_it():
    existing = DailyRecord(D0, deaths=0, feed_kg=100.0, treatments=(VACCINE,))
    corrected = _merge(existing, treatments=(MEDICINE,))
    assert corrected.treatments == (VACCINE, MEDICINE)


def test_an_exact_repeat_of_an_already_logged_treatment_is_not_duplicated():
    existing = DailyRecord(D0, deaths=0, feed_kg=100.0, treatments=(VACCINE,))
    corrected = _merge(existing, treatments=(VACCINE,))
    assert corrected.treatments == (VACCINE,)


def test_the_same_treatment_name_with_a_different_note_is_a_new_entry():
    existing = DailyRecord(D0, deaths=0, feed_kg=100.0, treatments=(MEDICINE,))
    other_dose_note = Treatment(TreatmentKind.MEDICINE, "Amoxicillin", note="2nd course")
    corrected = _merge(existing, treatments=(other_dose_note,))
    assert corrected.treatments == (MEDICINE, other_dose_note)


def test_omitting_every_field_reproduces_the_existing_record_unchanged():
    existing = DailyRecord(D0, deaths=5, feed_kg=100.0, avg_weight_g=1800.0, weight_sample_birds=10)
    assert _merge(existing) == existing


def test_an_existing_eggs_value_is_carried_over_even_though_this_tool_never_sets_it():
    existing = DailyRecord(D0, deaths=0, feed_kg=100.0, eggs=820)
    corrected = _merge(existing, deaths=1)
    assert corrected.eggs == 820


def test_validate_record_day_accepts_today_and_the_placement_day():
    house = broiler_house(feed_kg=[10.0])
    validate_record_day(house, D0, D0)  # placement day == today
    validate_record_day(house, D0, D0 + timedelta(days=5))  # placement day, later "today"


def test_validate_record_day_rejects_a_future_day():
    house = broiler_house(feed_kg=[10.0])
    with pytest.raises(RecordDayOutOfRange) as e:
        validate_record_day(house, D0 + timedelta(days=1), D0)
    assert "future" in e.value.customer_message


def test_validate_record_day_rejects_a_day_before_placement():
    house = layer_house(deaths=[0], feed_kg=[50.0])  # placed_on = D0
    with pytest.raises(RecordDayOutOfRange) as e:
        validate_record_day(house, D0 - timedelta(days=1), D0 + timedelta(days=5))
    assert "wasn't placed yet" in e.value.customer_message
