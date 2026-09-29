"""Farm data model. Immutable dataclasses, so domain math can't mutate shared state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class HouseKind(StrEnum):
    BROILER = "broiler"
    LAYER = "layer"


class TreatmentKind(StrEnum):
    MEDICINE = "medicine"
    VACCINE = "vaccine"


MAX_TREATMENT_NAME = 80
MAX_TREATMENT_NOTE = 200


@dataclass(frozen=True)
class Treatment:
    """A medicine or vaccine given to a house that day, by name only. There is deliberately no dose field:
    CluckTalk never stores or suggests doses (docs/DESIGN.md §7 rule 3, §13.2)."""

    kind: TreatmentKind
    name: str
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > MAX_TREATMENT_NAME:
            raise ValueError(f"treatment name must be 1-{MAX_TREATMENT_NAME} characters")
        if self.note is not None and len(self.note) > MAX_TREATMENT_NOTE:
            raise ValueError(f"treatment note must be at most {MAX_TREATMENT_NOTE} characters")


@dataclass(frozen=True)
class DailyRecord:
    """One day's readings for one house, as the farmer (or a sensor) logged them."""

    day: date
    deaths: int
    feed_kg: float  # feed consumed that day by the whole house
    avg_weight_g: float | None = None  # broilers: sample-weighing day only
    eggs: int | None = None  # layers only
    weight_sample_birds: int | None = None  # how many birds were weighed for avg_weight_g, when the farmer says
    treatments: tuple[Treatment, ...] = ()

    def __post_init__(self) -> None:
        if self.deaths < 0 or self.feed_kg < 0:
            raise ValueError(f"{self.day}: deaths and feed_kg must be >= 0")
        if self.avg_weight_g is not None and self.avg_weight_g <= 0:
            raise ValueError(f"{self.day}: avg_weight_g must be > 0")
        if self.eggs is not None and self.eggs < 0:
            raise ValueError(f"{self.day}: eggs must be >= 0")
        if self.weight_sample_birds is not None:
            if self.avg_weight_g is None:
                raise ValueError(f"{self.day}: weight_sample_birds needs avg_weight_g")
            if self.weight_sample_birds <= 0:
                raise ValueError(f"{self.day}: weight_sample_birds must be > 0")


@dataclass(frozen=True)
class House:
    house_id: str  # stable ID used across tools (docs/DESIGN.md §5, rule 5)
    number: int  # the farmer says "shed two" / "house 2" / "kotam 2"
    kind: HouseKind
    breed: str
    placed_on: date
    birds_placed: int
    age_at_placement_days: int  # 0 for day-old broiler chicks; pullet age for layers
    feed_stock_kg: float
    records: tuple[DailyRecord, ...]  # sorted by day, one per day at most

    def __post_init__(self) -> None:
        if self.birds_placed <= 0:
            raise ValueError(f"{self.house_id}: birds_placed must be > 0")
        if self.feed_stock_kg < 0:
            raise ValueError(f"{self.house_id}: feed_stock_kg must be >= 0")
        days = [r.day for r in self.records]
        if days != sorted(set(days)):
            raise ValueError(f"{self.house_id}: records must be sorted by day with no duplicates")
        if days and days[0] < self.placed_on:
            raise ValueError(f"{self.house_id}: a record predates placement")
        if sum(r.deaths for r in self.records) > self.birds_placed:
            raise ValueError(f"{self.house_id}: more deaths recorded than birds placed")

    @property
    def label_en(self) -> str:
        return f"House {self.number}"

    @property
    def label_te(self) -> str:
        return f"షెడ్ {self.number}"

    def records_until(self, as_of: date) -> tuple[DailyRecord, ...]:
        return tuple(r for r in self.records if r.day <= as_of)

    def age_days(self, as_of: date) -> int:
        return self.age_at_placement_days + (as_of - self.placed_on).days

    def live_birds(self, as_of: date) -> int:
        return self.birds_placed - sum(r.deaths for r in self.records_until(as_of))


@dataclass(frozen=True)
class Farm:
    farm_id: str
    name: str
    is_fictional: bool
    houses: tuple[House, ...]
    feed_price_per_kg: Decimal  # simulated market price, labeled as such in every output
    supplier_lead_days: int  # simulated supplier
    live_bird_price_per_kg: Decimal  # simulated default; a farmer's spoken rate overrides it per call

    def __post_init__(self) -> None:
        ids = [h.house_id for h in self.houses]
        numbers = [h.number for h in self.houses]
        if len(ids) != len(set(ids)) or len(numbers) != len(set(numbers)):
            raise ValueError(f"{self.farm_id}: house IDs and numbers must be unique")
        if self.feed_price_per_kg <= 0 or self.supplier_lead_days < 0:
            raise ValueError(f"{self.farm_id}: feed price must be > 0 and lead time >= 0")
        if self.live_bird_price_per_kg <= 0:
            raise ValueError(f"{self.farm_id}: live_bird_price_per_kg must be > 0")
