"""Farm profile: how the farm is run, which decides what CluckTalk offers (docs/DESIGN.md §13.1).

Contract farms get chicks, feed and medicine from a company (integrator) and are paid a growing charge, so
CluckTalk plans no feed purchases or sales for them. Independent farms buy their own feed and sell their own birds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
