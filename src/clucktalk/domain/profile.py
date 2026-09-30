"""Farm profile: how the farm is run, which decides what CluckTalk offers (docs/DESIGN.md §13.1).

Contract farms get chicks, feed and medicine from a company (integrator) and are paid a growing charge, so
CluckTalk plans no feed purchases or sales for them. Independent farms buy their own feed and sell their own birds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal


class FarmMode(StrEnum):
    CONTRACT = "contract"
    INDEPENDENT = "independent"


# The demo farm starts independent, so the seeded story (House 2 low on feed -> reorder) is told as designed.
DEMO_DEFAULT_MODE = FarmMode.INDEPENDENT

SetBy = Literal["demo_default", "farmer"]


@dataclass(frozen=True)
class FarmProfile:
    farm_id: str
    mode: FarmMode
    set_by: SetBy
    updated_at: datetime | None  # None for the demo default (never set by the farmer)

    def __post_init__(self) -> None:
        if (self.set_by == "farmer") != (self.updated_at is not None):
            raise ValueError(f"{self.farm_id}: a farmer-set profile needs updated_at; the demo default has none")


def demo_default_profile(farm_id: str) -> FarmProfile:
    return FarmProfile(farm_id=farm_id, mode=DEMO_DEFAULT_MODE, set_by="demo_default", updated_at=None)


FCR_POINT = Decimal("0.1")  # the incentive/deduction rates below are "per 0.1 FCR", a common contract-farming unit


@dataclass(frozen=True)
class ContractTerms:
    """The farmer's own contract terms (docs/DESIGN.md §13.3), entered by the farmer alone: never a named
    company's rates (CLAUDE.md safety rule). Used by plan_sale to show how an extra day changes the growing
    charge; the full Contract Earnings Tracker (sensitivity, what-if) is a separate, later tool."""

    farm_id: str
    base_rate_per_kg: Decimal  # rupees per kg live weight, at standard_fcr
    standard_fcr: Decimal
    incentive_per_kg_per_fcr_point: Decimal  # rupees added per kg, per 0.1 FCR better than standard
    deduction_per_kg_per_fcr_point: Decimal  # rupees subtracted per kg, per 0.1 FCR worse than standard
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.base_rate_per_kg <= 0 or self.standard_fcr <= 0:
            raise ValueError(f"{self.farm_id}: base_rate_per_kg and standard_fcr must be > 0")
        for name in ("incentive_per_kg_per_fcr_point", "deduction_per_kg_per_fcr_point"):
            if getattr(self, name) < 0:
                raise ValueError(f"{self.farm_id}: {name} must be >= 0")

    def rate_per_kg(self, actual_fcr: Decimal) -> Decimal:
        """Rupees per kg live weight at ``actual_fcr``, floored at 0 (never a negative payout)."""
        points = (actual_fcr - self.standard_fcr) / FCR_POINT
        if points > 0:
            return max(Decimal(0), self.base_rate_per_kg - points * self.deduction_per_kg_per_fcr_point)
        return self.base_rate_per_kg + (-points) * self.incentive_per_kg_per_fcr_point
