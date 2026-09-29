"""Voice Record Book: merge what the farmer says this call onto the day's already-saved record, so a one-field
correction ("actually it was 7, not 6") never silently wipes the rest of the day's numbers (docs/DESIGN.md §13.4).

Pure logic, no I/O: ``clucktalk.server.tools.records`` reads/writes the store around this.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from clucktalk.domain.errors import RecordDayOutOfRange, WeightSampleNeedsBirdCount
from clucktalk.domain.models import DailyRecord, House, Treatment


def validate_record_day(house: House, day: date, as_of: date) -> None:
    """A record's day must be on or after the house's placement, and never in the future."""
    if day > as_of or day < house.placed_on:
        raise RecordDayOutOfRange(house.label_en, house.label_te, day, as_of)


def overlay_house_records(house: House, overrides: dict[date, DailyRecord]) -> House:
    """Farmer-logged records (the voice record book) replace the seed's synthetic ones for the same day.

    The demo seed is generated fresh relative to "today" (CLAUDE.md, docs/DESIGN.md §10), so a house's whole
    placed_on..as_of window slides forward as real days pass. A logged day that has fallen outside that
    window is left out here rather than raising: `House` would otherwise reject it as predating placement,
    and a farmer's real record must never crash the farm status a session later. This is a known limitation
    of the sliding-seed design, not a bug in the record itself (docs/DESIGN.md §13.2)."""
    if not overrides:
        return house
    by_day = {r.day: r for r in house.records}
    changed = False
    for day, rec in overrides.items():
        if day in by_day:  # within the house's current placed_on..as_of window
            by_day[day] = rec
            changed = True
    return replace(house, records=tuple(by_day[d] for d in sorted(by_day))) if changed else house


def merge_daily_record(
    existing: DailyRecord | None,
    day: date,
    deaths: int | None,
    feed_kg: float | None,
    avg_weight_g: float | None,
    weight_sample_birds: int | None,
    treatments: tuple[Treatment, ...] | None,
    label_en: str,
    label_te: str,
) -> DailyRecord:
    """``None`` means "the farmer didn't mention this field this call": keep the day's saved value, if any.
    A given field (even 0) always overwrites. Treatments add to the day's list rather than replacing it (each
    is a separate event the farmer mentions once); an exact repeat of an already-logged treatment is dropped.

    ``avg_weight_g`` and ``weight_sample_birds`` are a pair. ``DailyRecord`` itself only rejects the reverse case
    (a bird count without a weight); the case this domain layer must additionally reject — a weight without a
    bird count — raises ``WeightSampleNeedsBirdCount`` here, with the house's own label.
    """
    if avg_weight_g is not None and weight_sample_birds is None:
        raise WeightSampleNeedsBirdCount(label_en, label_te)
    if avg_weight_g is not None:
        new_avg_weight_g, new_weight_sample_birds = avg_weight_g, weight_sample_birds
    else:
        new_avg_weight_g = existing.avg_weight_g if existing else None
        new_weight_sample_birds = existing.weight_sample_birds if existing else None
    existing_treatments = existing.treatments if existing else ()
    added = tuple(t for t in (treatments or ()) if t not in existing_treatments)
    return DailyRecord(
        day=day,
        deaths=deaths if deaths is not None else (existing.deaths if existing else 0),
        feed_kg=feed_kg if feed_kg is not None else (existing.feed_kg if existing else 0.0),
        avg_weight_g=new_avg_weight_g,
        eggs=existing.eggs if existing else None,  # broiler-first (CLAUDE.md): never set from this tool
        weight_sample_birds=new_weight_sample_birds,
        treatments=existing_treatments + added,
    )
