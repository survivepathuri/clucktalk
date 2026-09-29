"""ContractTerms.rate_per_kg (docs/DESIGN.md §13.3): a pure function of the farmer's own numbers, hand-computed."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from clucktalk.domain.profile import ContractTerms

T0 = datetime(2026, 9, 29, tzinfo=UTC)


def terms(**overrides) -> ContractTerms:
    defaults = dict(
        farm_id="farm-1",
        base_rate_per_kg=Decimal("100"),
        standard_fcr=Decimal("1.8"),
        mortality_allowance_pct=Decimal("5"),
        incentive_per_kg_per_fcr_point=Decimal("2"),
        deduction_per_kg_per_fcr_point=Decimal("3"),
        updated_at=T0,
    )
    return ContractTerms(**{**defaults, **overrides})


@pytest.mark.parametrize(
    ("actual_fcr", "expected"),
    [
        ("1.8", "100"),  # exactly standard: base rate
        ("1.9", "97"),  # 0.1 worse: -3
        ("2.0", "94"),  # 0.2 worse: -6
        ("1.7", "102"),  # 0.1 better: +2
        ("1.6", "104"),  # 0.2 better: +4
    ],
)
def test_rate_moves_by_the_stated_amount_per_01_fcr_point(actual_fcr, expected):
    assert terms().rate_per_kg(Decimal(actual_fcr)) == Decimal(expected)


def test_rate_never_goes_negative():
    t = terms(base_rate_per_kg=Decimal("10"), deduction_per_kg_per_fcr_point=Decimal("50"))
    assert t.rate_per_kg(Decimal("3.0")) == Decimal(0)  # far worse than standard: floored, not negative


@pytest.mark.parametrize(
    "bad",
    [
        {"base_rate_per_kg": Decimal(0)},
        {"base_rate_per_kg": Decimal(-5)},
        {"standard_fcr": Decimal(0)},
        {"mortality_allowance_pct": Decimal(-1)},
        {"incentive_per_kg_per_fcr_point": Decimal(-1)},
        {"deduction_per_kg_per_fcr_point": Decimal(-1)},
    ],
)
def test_invalid_terms_are_rejected(bad):
    with pytest.raises(ValueError):
        terms(**bad)
