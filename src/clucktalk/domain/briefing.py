"""Daily Briefing rules, pure (docs/DESIGN.md §18).

Code collects the facts (each from the record book, the feed and sale maths, or a stored health check) and orders
them by rules. A model may only re-order the facts that are NOT health facts, choosing from the closed list of their
ids; a health fact is pinned above everything and can never be moved (``apply_order``). There is no drug, dose or
treatment anywhere in this module, and no sale figure in rupees (a sale fact carries only a day, Simulated).
Telugu and English wording live in the tool (clucktalk.server.tools.briefing), rendered from these same values.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from clucktalk.domain.daily_deaths import DailyDeathsRule
from clucktalk.domain.errors import DomainError
from clucktalk.domain.feed import plan_feed
from clucktalk.domain.follow_up import FollowUp, FollowUpState
from clucktalk.domain.models import Farm, House
from clucktalk.domain.sale import plan_sale
from clucktalk.domain.status import Level, house_status, spike_finding
from clucktalk.domain.triage import CheckStatus, HealthCheck, Urgency

logger = logging.getLogger("clucktalk.domain")

# Voice rule (Alexa+): at most 5 items, so at most 5 ranked items ever leave the tool; the first 3 are read out and
# "more" reads the rest (user decision 2026-09-30).
MAX_ITEMS = 5
SPOKEN_ITEMS = 3
# CluckTalk's own choices (heuristics, not sourced): how long a past spike or triage stays worth mentioning, and how
# close to its best sale day a flock must be to be "in its sale window".
RECENT_SPIKE_DAYS = 7  # the same trailing week the status spike baseline uses
RECENT_CHECK_DAYS = 3
NOTIFIABLE_DAYS = 7  # a suspected reportable disease stays until a vet handoff was confirmed, or this many days
SALE_WINDOW_DAYS = 3


class Category(StrEnum):
    MORTALITY_SPIKE = "mortality_spike"
    RECENT_LOGGED_SPIKE = "recent_logged_spike"
    OPEN_HEALTH_CHECK = "open_health_check"
    FOLLOW_UP = "follow_up"
    CUM_MORTALITY_HIGH = "cum_mortality_high"
    DAILY_DEATHS_RULE = "daily_deaths_rule"  # the farmer's own limit (Step 51); it can only raise to WATCH
    WEIGHT_BELOW_TARGET = "weight_below_target"
    FCR_ABOVE_TARGET = "fcr_above_target"
    LAYING_DROP = "laying_drop"
    FEED_INTAKE_DROP = "feed_intake_drop"
    FEED_STOCK_LOW = "feed_stock_low"
    RECORDS_STALE = "records_stale"
    NOT_CHECKED = "not_checked"
    SALE_WINDOW = "sale_window"
    NOT_LOGGED_TODAY = "not_logged_today"


# The order of kinds when two facts tie on severity: health first, then production, then housekeeping.
CATEGORY_ORDER = tuple(Category)

# Status findings that become facts (the code of the finding is the category).
STATUS_CATEGORIES = {
    Category.MORTALITY_SPIKE,
    Category.CUM_MORTALITY_HIGH,
    Category.DAILY_DEATHS_RULE,
    Category.WEIGHT_BELOW_TARGET,
    Category.FCR_ABOVE_TARGET,
    Category.LAYING_DROP,
    Category.FEED_INTAKE_DROP,
    Category.RECORDS_STALE,
}
# Severity of a stored health check, above every level (0-2): an urgent vet check outranks the mortality alerts, and a
# suspected reportable disease outranks everything (Rule 11 review 2026-09-30, M2).
URGENT_CHECK_SEVERITY = 3
NOTIFIABLE_SEVERITY = 4
# Every health fact is pinned, at any level: above every non-health item, never re-ordered by a model.
HEALTH_CATEGORIES = frozenset(
    {
        Category.MORTALITY_SPIKE,
        Category.RECENT_LOGGED_SPIKE,
        Category.OPEN_HEALTH_CHECK,
        Category.FOLLOW_UP,
        Category.CUM_MORTALITY_HIGH,
        Category.DAILY_DEATHS_RULE,
    }
)


@dataclass(frozen=True)
class Fact:
    fact_id: str  # "<category>:<house_id>" ("farm" for a farm-level fact): the only thing a model may name
    category: Category
    level: Level
    severity: int  # the level, or NOTIFIABLE_SEVERITY for a suspected reportable disease
    pinned: bool  # a health fact (any level): above everything, never re-ordered by a model
    house_id: str | None
    number: int | None  # the house number, for tie-breaks and speech
    values: dict[str, Any]  # the numbers behind the fact; the tool renders every sentence from these
    simulated: bool = False  # built on simulated data (the sale item); labelled so in every output
    is_today: bool = True  # status facts only: is the latest record from today (wording)
    tiebreak: float = 0.0  # smaller first among equals (days of feed left)


def _fact_id(category: Category, house_id: str | None) -> str:
    return f"{category.value}:{house_id or 'farm'}"


def _severity(level: Level) -> int:
    return int(level)


def _answered(check: HealthCheck) -> bool:
    return check.status is CheckStatus.READY and check.result is not None


def check_urgency(check: HealthCheck) -> Urgency:
    """What the farmer was told: the model's answer, or (still running, or it could not answer) the code floor,
    the same level ``get_health_check`` speaks. The briefing must never say less than the health tool."""
    return check.result.urgency if check.result is not None else check.floor.urgency


def _check_to_show(
    as_of: date, latest: HealthCheck | None, recent: Sequence[HealthCheck], handed_off: frozenset[str]
) -> HealthCheck | None:
    """The one stored check a house's briefing item is built from. A suspected reportable disease is not hidden by a
    newer check (routine, running or failed): the newest one not yet handed to a vet stays for NOTIFIABLE_DAYS. Any
    other check counts only if it is the house's latest, within RECENT_CHECK_DAYS, and at least a watch."""

    def age(c: HealthCheck) -> int:
        return max(0, (as_of - c.created_at.date()).days)

    def handed(c: HealthCheck) -> bool:
        return check_urgency(c) is Urgency.NOTIFIABLE_SUSPECT and c.check_id in handed_off

    pool = list(recent)
    if latest is not None and all(c.check_id != latest.check_id for c in pool):
        pool.append(latest)
    notifiable = [
        c
        for c in pool
        if check_urgency(c) is Urgency.NOTIFIABLE_SUSPECT and not handed(c) and age(c) <= NOTIFIABLE_DAYS
    ]
    if notifiable:
        return max(notifiable, key=lambda c: c.created_at)
    # An URGENT check is not hidden by a newer check of lower urgency either (review finding H3, together with the
    # follow-up rule): the newest urgent check stays for RECENT_CHECK_DAYS. A newer urgent check simply is the newest;
    # a newer suspected reportable disease (here only one already handed to a vet) takes it over, as in the follow-up.
    urgent = [
        c
        for c in pool
        if check_urgency(c) is Urgency.URGENT
        and age(c) <= RECENT_CHECK_DAYS
        and not any(check_urgency(n) is Urgency.NOTIFIABLE_SUSPECT and n.created_at > c.created_at for n in pool)
    ]
    if urgent:
        return max(urgent, key=lambda c: c.created_at)
    if latest is None or handed(latest):
        return None
    if check_urgency(latest) >= Urgency.WATCH and age(latest) <= RECENT_CHECK_DAYS:
        return latest
    return None


def _follow_up_fact(house: House, as_of: date, fup: FollowUp | None, replaced: Fact | None) -> Fact | None:
    """The follow-up item for a shed: a pinned alert when it is escalated, a pinned question when it is due and still
    unanswered. Nothing for any other state. Its priority is the check's own (a reportable suspect 4, an urgent check
    3, an escalated watch check 3, a due watch check as a watch), and never below the item it replaces. The days since
    the check come from ``as_of``, the date passed in."""
    if fup is None or fup.check_day is None or fup.state not in (FollowUpState.ESCALATED, FollowUpState.DUE):
        return None
    urgent = fup.urgency >= Urgency.URGENT
    if fup.state is FollowUpState.ESCALATED or urgent:
        level = Level.ALERT
    else:
        level = Level.WATCH
    severity = _severity(level)
    if fup.urgency is Urgency.NOTIFIABLE_SUSPECT:
        severity = NOTIFIABLE_SEVERITY
    elif urgent or fup.state is FollowUpState.ESCALATED:
        severity = URGENT_CHECK_SEVERITY
    if replaced is not None:
        level, severity = max(level, replaced.level), max(severity, replaced.severity)
    return Fact(
        _fact_id(Category.FOLLOW_UP, house.house_id),
        Category.FOLLOW_UP,
        level,
        severity,
        True,
        house.house_id,
        house.number,
        {"state": fup.state.value, "urgency": fup.urgency.code, "days_ago": max(0, (as_of - fup.check_day).days)},
    )


def health_fact(
    house: House,
    as_of: date,
    check: HealthCheck | None,
    recent: Sequence[HealthCheck],
    handed_off: Collection[str],
    follow_up: FollowUp | None = None,
) -> Fact | None:
    """The one health item for a shed from its stored checks and follow-up: its open health check, or (replacing it,
    never both) an escalated or due follow-up that is never lower than the check item. The briefing lists it and the
    farm status takes its level from it, so the two always agree for the same shed and day (review finding H1)."""
    shown = _check_to_show(as_of, check, recent, handed_off)
    if shown is None:
        open_check = None
    else:
        urgency = check_urgency(shown)
        days_ago = max(0, (as_of - shown.created_at.date()).days)
        urgent = urgency >= Urgency.URGENT
        level = Level.ALERT if urgent else Level.WATCH
        severity = _severity(level)
        if urgency is Urgency.NOTIFIABLE_SUSPECT:
            severity = NOTIFIABLE_SEVERITY
        elif urgent:
            severity = URGENT_CHECK_SEVERITY
        open_check = Fact(
            _fact_id(Category.OPEN_HEALTH_CHECK, house.house_id),
            Category.OPEN_HEALTH_CHECK,
            level,
            severity,
            True,
            house.house_id,
            house.number,
            {"urgency": urgency.code, "days_ago": days_ago, "ready": _answered(shown)},
        )
    # An escalated or due follow-up replaces this shed's open health-check item (never both): it is the one item the
    # farmer needs for this shed, and it never ranks lower than the check item it replaces.
    follow_fact = _follow_up_fact(house, as_of, follow_up, open_check)
    return follow_fact if follow_fact is not None else open_check


def recent_spike_fact(house: House, as_of: date) -> Fact | None:
    """The most recent death spike logged on an earlier day inside the trailing week (not the latest record's own
    count, which is the status's mortality_spike). The briefing lists it and the farm status shows it too, so the two
    agree on the shed's level (Step 48D)."""
    records = house.records_until(as_of)
    latest = records[-1]  # the caller has a status for this house, so there is at least one record
    for rec in reversed(records):
        if rec.day >= latest.day:
            continue
        if (as_of - rec.day).days > RECENT_SPIKE_DAYS - 1:
            break
        spike = spike_finding(house, records, rec)
        if spike is not None:
            return Fact(
                _fact_id(Category.RECENT_LOGGED_SPIKE, house.house_id),
                Category.RECENT_LOGGED_SPIKE,
                Level.ALERT,
                _severity(Level.ALERT),
                True,
                house.house_id,
                house.number,
                {**spike.values, "days_ago": (as_of - rec.day).days},
            )
    return None


def _house_facts(
    farm: Farm,
    house: House,
    as_of: date,
    check: HealthCheck | None,
    recent: Sequence[HealthCheck],
    handed_off: Collection[str],
    follow_up: FollowUp | None = None,
    deaths_rule: DailyDeathsRule | None = None,
) -> list[Fact]:
    try:
        st = house_status(house, as_of, deaths_rule)
    except DomainError as err:  # said, never hidden (Rule 6): the farmer hears this house was not checked
        return [
            Fact(
                _fact_id(Category.NOT_CHECKED, house.house_id),
                Category.NOT_CHECKED,
                Level.WATCH,
                _severity(Level.WATCH),
                False,
                house.house_id,
                house.number,
                {"message_en": err.customer_message, "message_te": err.customer_message_te},
            )
        ]
    facts: list[Fact] = []
    is_today = st.latest_record_day == as_of
    for f in st.findings:
        if f.level is Level.OK or f.code not in {c.value for c in STATUS_CATEGORIES}:
            continue  # "no reference curve" / "past the growth table" are notes, not things needing attention
        cat = Category(f.code)
        pinned = cat in HEALTH_CATEGORIES
        facts.append(
            Fact(
                _fact_id(cat, house.house_id),
                cat,
                f.level,
                _severity(f.level),
                pinned,
                house.house_id,
                house.number,
                dict(f.values),
                is_today=is_today,
            )
        )

    recent_spike = recent_spike_fact(house, as_of)
    if recent_spike is not None:
        facts.append(recent_spike)

    health = health_fact(house, as_of, check, recent, handed_off, follow_up)
    if health is not None:
        facts.append(health)

    try:
        plan = plan_feed(farm, house, as_of)
        if plan.reorder_needed:
            facts.append(
                Fact(
                    _fact_id(Category.FEED_STOCK_LOW, house.house_id),
                    Category.FEED_STOCK_LOW,
                    Level.WATCH,
                    _severity(Level.WATCH),
                    False,
                    house.house_id,
                    house.number,
                    {"days_covered": plan.days_covered, "stock_kg": plan.stock_kg},
                    tiebreak=float(plan.days_covered),
                )
            )
    except DomainError as err:
        logger.info("briefing for %s: feed cover unavailable (%s)", house.house_id, err.customer_message)

    try:
        sale = plan_sale(farm, house, as_of)
        if sale.best_day_index <= SALE_WINDOW_DAYS:
            facts.append(
                Fact(
                    _fact_id(Category.SALE_WINDOW, house.house_id),
                    Category.SALE_WINDOW,
                    Level.WATCH,
                    _severity(Level.WATCH),
                    False,
                    house.house_id,
                    house.number,
                    {"best_day_index": sale.best_day_index, "best_day": sale.days[sale.best_day_index].day.isoformat()},
                    simulated=True,
                )
            )
    except DomainError as err:  # layers, no curve, past the growth table: no sale item, and that is fine
        logger.info("briefing for %s: no sale item (%s)", house.house_id, err.customer_message)
    return facts


def _sort_key(f: Fact) -> tuple:
    return (not f.pinned, -f.severity, CATEGORY_ORDER.index(f.category), f.tiebreak, f.number or 0, f.fact_id)


def rules_order(facts: Iterable[Fact]) -> tuple[Fact, ...]:
    """Health (pinned) first, most severe first; then by severity, kind, and house. Independent of input order."""
    return tuple(sorted(facts, key=_sort_key))


def collect_facts(
    farm: Farm,
    as_of: date,
    checks: Mapping[str, HealthCheck],
    logged_today: frozenset[str],
    recent_checks: Mapping[str, Sequence[HealthCheck]] | None = None,
    handed_off: Collection[str] = frozenset(),
    follow_ups: Mapping[str, FollowUp] | None = None,
    deaths_rule: DailyDeathsRule | None = None,
) -> tuple[Fact, ...]:
    """Every fact worth mentioning today, in rules order. ``checks``: each house's latest health check, if any;
    ``recent_checks``: each house's checks from the last NOTIFIABLE_DAYS days; ``handed_off``: ids of checks whose vet
    handoff was confirmed; ``logged_today``: the houses that have a record for today in the record book;
    ``follow_ups``: each house's follow-up worth surfacing (computed by the caller from stored data and ``as_of``): an
    escalated one, or a due unanswered one, replaces that shed's open health-check item."""
    recent_checks = recent_checks or {}
    follow_ups = follow_ups or {}
    facts: list[Fact] = []
    for house in sorted(farm.houses, key=lambda h: h.number):
        facts += _house_facts(
            farm,
            house,
            as_of,
            checks.get(house.house_id),
            recent_checks.get(house.house_id, ()),
            handed_off,
            follow_ups.get(house.house_id),
            deaths_rule,
        )
    missing = [h.number for h in sorted(farm.houses, key=lambda h: h.number) if h.house_id not in logged_today]
    if missing:
        facts.append(
            Fact(
                _fact_id(Category.NOT_LOGGED_TODAY, None),
                Category.NOT_LOGGED_TODAY,
                Level.OK,
                _severity(Level.OK),
                False,
                None,
                None,
                {"count": len(missing), "numbers": missing},
            )
        )
    return rules_order(facts)


def apply_order(rules_ordered: tuple[Fact, ...], model_order: Any) -> tuple[Fact, ...]:
    """The final order. Pinned facts keep their rules order and stay first; the model's ids order the rest;
    anything it left out (or named twice, or that is not on the list, or is not even a string) follows in rules order.
    Never drops a fact and never raises on a damaged ordering (a stored one may be corrupt)."""
    pinned = [f for f in rules_ordered if f.pinned]
    rest = {f.fact_id: f for f in rules_ordered if not f.pinned}
    ordered: list[Fact] = []
    ids = list(model_order) if isinstance(model_order, (list, tuple)) else []  # a string or a dict is no ordering
    for fid in ids:
        fact = rest.pop(fid, None) if isinstance(fid, str) else None
        if fact is not None:
            ordered.append(fact)
    return tuple(pinned + ordered + [f for f in rules_ordered if f.fact_id in rest])


def fingerprint(facts: Iterable[Fact]) -> str:
    """Identifies exactly what the facts say. A stored ranking is only used for the same fingerprint."""
    rows = sorted(
        [f.fact_id, int(f.level), f.severity, f.pinned, f.values, f.is_today, f.tiebreak, f.simulated] for f in facts
    )
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


# -- the model's closed-list decision --------------------------------------------------------------------------------
class InvalidRanking(ValueError):
    """The model's reply is not exactly the closed-list schema."""


def ranking_schema(ids: list[str]) -> dict[str, Any]:
    """One array of ids from the offered list; no other field, so there is nowhere to put free text."""
    return {
        "type": "object",
        "properties": {
            "order": {
                "type": "array",
                "items": {"type": "string", "enum": list(ids)},
                "uniqueItems": True,
                "maxItems": len(ids),
            }
        },
        "required": ["order"],
        "additionalProperties": False,
    }


def validate_ranking(data: Any, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(data, dict) or set(data) != {"order"}:
        raise InvalidRanking("the reply must be an object with exactly one field, 'order'")
    order = data["order"]
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        raise InvalidRanking("'order' must be a list of ids")
    if len(set(order)) != len(order):
        raise InvalidRanking("'order' names an id twice")
    unknown = [x for x in order if x not in allowed]
    if unknown:
        raise InvalidRanking("'order' names an id that was not offered")
    return tuple(order)


@dataclass(frozen=True)
class BriefingRank:
    """A stored AI ordering of the non-health facts, valid for one day and one exact set of facts."""

    farm_id: str
    day: date
    fingerprint: str
    order: tuple[str, ...]
    engine: str
    model_id: str | None
    note: str | None  # None | "daily_limit" | "unreadable" (the stored row was damaged; its order is empty)
