import pytest

from clucktalk.domain.errors import NoReferenceCurve
from clucktalk.domain.reference import curve_for


@pytest.fixture
def ross():
    return curve_for("Ross 308")


def test_checkpoints_match_cited_table(ross):
    # Aviagen Ross 308 Performance Objectives 2022, As-Hatched, metric.
    assert ross.weight_g(0) == 44
    assert ross.weight_g(7) == 213
    assert ross.weight_g(35) == 2296
    assert ross.daily_intake_g(42) == 207
    assert ross.cum_intake_g(56) == 7733


def test_between_checkpoints_is_linear_interpolation(ross):
    # day 10: 213 + 3/7 * (533 - 213)
    assert ross.weight_g(10) == pytest.approx(213 + 3 / 7 * 320)
    # day 4 intake: 12 (day 1) + 3/6 * (35 - 12)
    assert ross.daily_intake_g(4) == pytest.approx(23.5)


def test_day_zero_intake_uses_day_one(ross):
    assert ross.daily_intake_g(0) == 12


def test_target_fcr_is_cum_intake_over_weight(ross):
    assert ross.target_fcr(35) == pytest.approx(3211 / 2296)


def test_outside_curve_raises(ross):
    with pytest.raises(ValueError):
        ross.weight_g(57)


@pytest.mark.parametrize("name", ["ross", "ROSS 308", "ross308"])
def test_breed_synonyms(name):
    assert curve_for(name).breed == "Ross 308"


def test_unsourced_breed_is_refused_not_substituted():
    # Cobb 430 has no cited public curve yet; never fall back to Ross silently (Rule 6).
    with pytest.raises(NoReferenceCurve):
        curve_for("Cobb 430")
