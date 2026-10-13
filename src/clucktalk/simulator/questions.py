"""The Questions button on the pilot page: answers built ONLY from what the farmer himself declared in the farm file's
``farmer_schedule`` and from his sheds' placement dates. No model, no tool call, no free text, no advice: each answer
starts with "As you told us:" because it is his own routine read back, not a checked fact.

A question whose data is absent from the file is not offered. His day N is the repository's age N-1 (age 0 is the
arrival day, which he counts as day 1).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from clucktalk.domain.models import HouseKind
from clucktalk.i18n import Text
from clucktalk.i18n.pilot import (
    ANSWER_DAY,
    ANSWER_DAY_45,
    ANSWER_FEED,
    ANSWER_LIGHTS_ON,
    ANSWER_LIGHTS_OVER,
    ANSWER_NEXT_VACCINE,
    ANSWER_SPRAY,
    ANSWER_VACCINE_NO,
    ANSWER_VACCINE_TODAY_NEXT,
    ANSWER_VACCINE_YES,
    ANSWER_VACCINES_OVER,
    ANSWER_VET,
    ANSWER_VET_DAILY,
    ANSWER_WEIGH_FROM,
    ANSWER_WEIGH_OK,
    ANSWER_WEIGHT,
    AS_TOLD,
    NO_FLOCK,
    QUESTION_LABELS,
    SHED_LABEL,
)
from clucktalk.pilot import FarmerSchedule, PilotFarmConfig

FINAL_DAY = 45  # the day the farmer's "_45d" figures and his day-45 date refer to


def _n(value: Decimal) -> str:
    return f"{value.normalize():f}"


def available(schedule: FarmerSchedule | None) -> list[int]:
    """The question numbers whose data the farmer gave, in the page's order."""
    if schedule is None:
        return []
    needs = {
        1: True,
        2: schedule.vaccination_farmer_days is not None,
        3: schedule.vaccination_farmer_days is not None,
        4: schedule.weigh_from_farmer_day is not None,
        5: schedule.spray_water_above_c is not None,
        6: schedule.heat_lights_first_days is not None,
        7: schedule.vet_visit_every_days is not None,
        8: schedule.normal_feed_per_bird_kg_45d is not None,
        9: schedule.normal_weight_kg_45d is not None,
        10: schedule.normal_feed_per_bird_kg_45d is not None or schedule.normal_weight_kg_45d is not None,
    }
    return [q for q, ok in needs.items() if ok]


def labels(schedule: FarmerSchedule | None) -> list[dict[str, object]]:
    return [{"id": q, "en": QUESTION_LABELS[q].en, "te": QUESTION_LABELS[q].te} for q in available(schedule)]


def farmer_day(placed_on: date, age_at_placement: int, today: date) -> int:
    return age_at_placement + (today - placed_on).days + 1


def _join(lines: list[Text]) -> Text:
    return Text(
        " ".join([AS_TOLD.en, *(t.en for t in lines)]),
        " ".join([AS_TOLD.te, *(t.te for t in lines)]),
    )


def _fmt(text: Text, **values: object) -> Text:
    return Text(text.en.format(**values), text.te.format(**values))


def answer(config: PilotFarmConfig, today: date, question: int) -> Text | None:
    """The answer to one question, or None when it is not one of the offered questions."""
    sched = config.schedule
    if question not in available(sched) or sched is None:
        return None
    flocks = []
    for spec in config.houses:
        if spec.kind is not HouseKind.BROILER:
            continue
        day = farmer_day(spec.placed_on, spec.age_at_placement_days, today)
        if day >= 1:
            label = _fmt(SHED_LABEL, number=spec.number)
            flocks.append((spec, day, {"shed": label.en}, {"shed": label.te}))
    lines: list[Text] = []
    per_shed = question in (1, 2, 3, 6, 10)
    if per_shed and not flocks:
        return _join([NO_FLOCK])
    for spec, day, en, te in flocks if per_shed else []:
        lines.append(_per_shed(question, sched, spec, day, en, te))
    if question == 4:
        assert sched.weigh_from_farmer_day is not None
        lines.append(_fmt(ANSWER_WEIGH_FROM, day=sched.weigh_from_farmer_day))
        if sched.weight_ok_above_kg_at_day_40 is not None:
            lines.append(_fmt(ANSWER_WEIGH_OK, kg=_n(sched.weight_ok_above_kg_at_day_40)))
    elif question == 5:
        assert sched.spray_water_above_c is not None
        lines.append(_fmt(ANSWER_SPRAY, degrees=_n(sched.spray_water_above_c)))
    elif question == 7:
        assert sched.vet_visit_every_days is not None
        every = sched.vet_visit_every_days
        lines.append(ANSWER_VET_DAILY if every == 1 else _fmt(ANSWER_VET, days=every))
    elif question == 8:
        assert sched.normal_feed_per_bird_kg_45d is not None
        lines.append(_fmt(ANSWER_FEED, kg=_n(sched.normal_feed_per_bird_kg_45d)))
    elif question == 9:
        assert sched.normal_weight_kg_45d is not None
        lines.append(_fmt(ANSWER_WEIGHT, kg=_n(sched.normal_weight_kg_45d)))
    return _join(lines)


def _per_shed(question: int, sched: FarmerSchedule, spec, day: int, en: dict[str, str], te: dict[str, str]) -> Text:
    def both(text: Text, **values: object) -> Text:
        return Text(text.en.format(**en, **values), text.te.format(**te, **values))

    if question == 1:
        return both(ANSWER_DAY, day=day)
    if question == 2:
        assert sched.vaccination_farmer_days is not None
        later = [d for d in sched.vaccination_farmer_days if d >= day]
        if not later:
            return both(ANSWER_VACCINES_OVER)
        if later[0] == day:
            return both(ANSWER_VACCINE_TODAY_NEXT, day=day)
        return both(ANSWER_NEXT_VACCINE, day=later[0], left=later[0] - day)
    if question == 3:
        assert sched.vaccination_farmer_days is not None
        return both(ANSWER_VACCINE_YES if day in sched.vaccination_farmer_days else ANSWER_VACCINE_NO, day=day)
    if question == 6:
        assert sched.heat_lights_first_days is not None
        days = sched.heat_lights_first_days
        return both(ANSWER_LIGHTS_ON if day <= days else ANSWER_LIGHTS_OVER, days=days, day=day)
    due = spec.placed_on + timedelta(days=FINAL_DAY - 1 - spec.age_at_placement_days)
    return both(ANSWER_DAY_45, date=due.strftime("%d-%m-%Y"))
