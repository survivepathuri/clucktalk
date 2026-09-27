"""Breed reference curves (target weight and feed by age), loaded from cited data files in data/reference/.

A breed is only supported if a sourced curve file exists. Unknown breeds raise NoReferenceCurve.
CluckTalk never substitutes another breed's curve silently (Rule 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from clucktalk.config import DATA_DIR
from clucktalk.domain.errors import NoReferenceCurve

REFERENCE_DIR = DATA_DIR / "reference"


@dataclass(frozen=True)
class CurvePoint:
    day: int
    weight_g: float
    daily_intake_g: float | None
    cum_intake_g: float


@dataclass(frozen=True)
class ReferenceCurve:
    breed: str
    synonyms: tuple[str, ...]
    source_title: str
    points: tuple[CurvePoint, ...]

    @property
    def max_day(self) -> int:
        return self.points[-1].day

    def _interpolate(self, day: float, field: str) -> float:
        pts = [p for p in self.points if getattr(p, field) is not None]
        if day < pts[0].day or day > pts[-1].day:
            raise ValueError(f"day {day} is outside the {self.breed} curve ({pts[0].day}-{pts[-1].day})")
        for lo, hi in zip(pts, pts[1:], strict=False):
            if lo.day <= day <= hi.day:
                frac = (day - lo.day) / (hi.day - lo.day)
                return getattr(lo, field) + frac * (getattr(hi, field) - getattr(lo, field))
        return getattr(pts[-1], field)

    def weight_g(self, day: float) -> float:
        return self._interpolate(day, "weight_g")

    def daily_intake_g(self, day: float) -> float:
        # Day 0 has no intake row; chicks eat from placement, so day-0 intake uses the day-1 value.
        return self._interpolate(max(day, self.points[1].day), "daily_intake_g")

    def cum_intake_g(self, day: float) -> float:
        return self._interpolate(day, "cum_intake_g")

    def target_fcr(self, day: float) -> float:
        """Publisher definition: cumulative intake per living bird / body weight."""
        return self.cum_intake_g(day) / self.weight_g(day)


def _parse(path: Path) -> ReferenceCurve:
    raw = json.loads(path.read_text(encoding="utf-8"))
    points = tuple(
        CurvePoint(p["day"], float(p["weight_g"]), p["daily_intake_g"], float(p["cum_intake_g"])) for p in raw["points"]
    )
    days = [p.day for p in points]
    if days != sorted(set(days)) or len(points) < 2:
        raise ValueError(f"{path.name}: curve points must be >= 2 and strictly increasing by day")
    return ReferenceCurve(
        breed=raw["breed"],
        synonyms=tuple(s.lower() for s in raw["breed_synonyms"]),
        source_title=raw["source"]["title"],
        points=points,
    )


@cache
def _all_curves(directory: Path = REFERENCE_DIR) -> tuple[ReferenceCurve, ...]:
    return tuple(_parse(p) for p in sorted(directory.glob("*.json")))


def curve_for(breed: str, directory: Path = REFERENCE_DIR) -> ReferenceCurve:
    key = breed.strip().lower()
    for curve in _all_curves(directory):
        if key == curve.breed.lower() or key in curve.synonyms:
            return curve
    raise NoReferenceCurve(breed)
