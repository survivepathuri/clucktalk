"""Per-house status: flock numbers plus ranked findings. Pure function of (house, as_of).

Returns structured data only. Spoken and card text (text_en / text_te) are rendered from these same
numbers in the tool layer, so voice and screen cannot disagree (docs/DESIGN.md §6, cross-modal).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import IntEnum

from clucktalk.domain import thresholds as t
from clucktalk.domain.daily_deaths import DailyDeathsRule
from clucktalk.domain.daily_deaths import evaluate as evaluate_deaths_rule
from clucktalk.domain.errors import InsufficientData, NoReferenceCurve
from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.reference import curve_for


class Level(IntEnum):
    OK = 0
    WATCH = 1
    ALERT = 2


@dataclass(frozen=True)
class Finding:
    code: str  # stable machine code, never spoken
    level: Level
    values: dict[str, float | int | str]  # the numbers behind the finding, for text rendering and cards


@dataclass(frozen=True)
class HouseStatus:
    house_id: str
    label_en: str
    label_te: str
    kind: HouseKind
    breed: str
    as_of: date
    latest_record_day: date
    age_days: int
    birds_placed: int
    live_birds: int
    deaths_latest: int
    deaths_7d: int
    cum_mortality_pct: float
    feed_latest_kg: float
    feed_per_bird_latest_g: float
    # Broilers (None when no weighing yet)
    avg_weight_g: float | None
    weight_day: date | None
    target_weight_g: float | None
    farm_fcr: float | None
    target_fcr: float | None
    # Layers
    hen_day_pct: float | None
    hen_day_pct_7d_avg: float | None
    findings: tuple[Finding, ...]

    @property
    def level(self) -> Level:
        return max((f.level for f in self.findings), default=Level.OK)


def _live_at_start_of(house: House, day: date) -> int:
    return house.live_birds(day - timedelta(days=1))


def _mortality_findings(house: House, records: tuple[DailyRecord, ...], latest: DailyRecord) -> list[Finding]:
    findings = []
    cum_pct = 100 * (house.birds_placed - house.live_birds(latest.day)) / house.birds_placed
    if cum_pct >= t.CUM_MORTALITY_WATCH_PCT:
        level = Level.ALERT if cum_pct >= t.CUM_MORTALITY_ALERT_PCT else Level.WATCH
        findings.append(Finding("cum_mortality_high", level, {"cum_mortality_pct": round(cum_pct, 2)}))

    spike = spike_finding(house, records, latest)
    if spike:
        findings.append(spike)
    return findings


def spike_finding(house: House, records: tuple[DailyRecord, ...], record: DailyRecord) -> Finding | None:
    """Was ``record`` a death spike against the 7 days before it? Used for the latest day (status) and, by the
    Daily Briefing, for an earlier logged day that is still inside the recall window."""
    prior = [r for r in records if record.day - timedelta(days=7) <= r.day < record.day]
    if len(prior) < t.MIN_BASELINE_DAYS:
        return None
    baseline = sum(r.deaths for r in prior) / len(prior)
    floor = max(
        math.ceil(t.MORTALITY_SPIKE_MIN_FRACTION * _live_at_start_of(house, record.day)),
        t.MORTALITY_SPIKE_MIN_BIRDS,
    )
    if record.deaths < max(t.MORTALITY_SPIKE_FACTOR * baseline, floor):
        return None
    return Finding(
        "mortality_spike",
        Level.ALERT,
        {"deaths": record.deaths, "baseline_daily_avg": round(baseline, 1), "day": record.day.isoformat()},
    )


def _per_bird_g(house: House, record: DailyRecord) -> float:
    return 1000 * record.feed_kg / _live_at_start_of(house, record.day)


def _feed_drop_finding(house: House, records: tuple[DailyRecord, ...], latest: DailyRecord) -> Finding | None:
    """Compare today's intake with the recent past. Broiler intake grows every day, so broilers are
    compared as a ratio to the breed curve at each day's age. Layers eat a flat amount and are compared directly."""
    prior = [r for r in records if r.day < latest.day][-t.FEED_BASELINE_DAYS :]
    if len(prior) < t.FEED_BASELINE_DAYS:
        return None
    if house.kind is HouseKind.BROILER:
        curve = curve_for(house.breed)
        if house.age_days(latest.day) > curve.max_day:
            return None  # no target beyond the curve; the status reports target_weight_g=None

        def norm(r: DailyRecord) -> float:
            return _per_bird_g(house, r) / curve.daily_intake_g(house.age_days(r.day))
    else:

        def norm(r: DailyRecord) -> float:
            return _per_bird_g(house, r)

    baseline = sum(norm(r) for r in prior) / len(prior)
    today = norm(latest)
    if baseline > 0 and today < t.FEED_DROP_WATCH_RATIO * baseline:
        expected_g = _per_bird_g(house, latest) * baseline / today
        return Finding(
            "feed_intake_drop",
            Level.WATCH,
            {
                "per_bird_g": round(_per_bird_g(house, latest), 1),
                "expected_per_bird_g": round(expected_g, 1),
                "drop_pct": round(100 * (1 - today / baseline), 1),
            },
        )
    return None


def _broiler_growth(house: House, records: tuple[DailyRecord, ...]):
    weighed = [r for r in records if r.avg_weight_g is not None]
    if not weighed:
        return None, None, None, None, None, []
    w = weighed[-1]
    curve = curve_for(house.breed)
    age = house.age_days(w.day)
    if age > curve.max_day:
        return w.avg_weight_g, w.day, None, None, None, []
    target_w = curve.weight_g(age)
    findings = []
    ratio = w.avg_weight_g / target_w
    if ratio < t.WEIGHT_WATCH_RATIO:
        level = Level.ALERT if ratio < t.WEIGHT_ALERT_RATIO else Level.WATCH
        findings.append(
            Finding(
                "weight_below_target",
                level,
                {
                    "avg_weight_g": w.avg_weight_g,
                    "target_weight_g": round(target_w),
                    "pct_of_target": round(100 * ratio, 1),
                },
            )
        )
    cum_feed_kg = sum(r.feed_kg for r in records if r.day <= w.day)
    live_kg = house.live_birds(w.day) * w.avg_weight_g / 1000
    farm_fcr = cum_feed_kg / live_kg
    target_fcr = curve.target_fcr(age)
    if farm_fcr > target_fcr + t.FCR_WATCH_MARGIN:
        findings.append(
            Finding(
                "fcr_above_target", Level.WATCH, {"farm_fcr": round(farm_fcr, 2), "target_fcr": round(target_fcr, 2)}
            )
        )
    return w.avg_weight_g, w.day, round(target_w), round(farm_fcr, 3), round(target_fcr, 3), findings


def _layer_production(house: House, records: tuple[DailyRecord, ...], latest: DailyRecord):
    if latest.eggs is None:
        return None, None, []
    today_pct = 100 * latest.eggs / _live_at_start_of(house, latest.day)
    prior = [r for r in records if latest.day - timedelta(days=7) <= r.day < latest.day and r.eggs is not None]
    if len(prior) < t.MIN_BASELINE_DAYS:
        return round(today_pct, 1), None, []
    avg = sum(100 * r.eggs / _live_at_start_of(house, r.day) for r in prior) / len(prior)
    drop = avg - today_pct
    findings = []
    if drop >= t.LAYING_DROP_WATCH_PTS:
        level = Level.ALERT if drop >= t.LAYING_DROP_ALERT_PTS else Level.WATCH
        findings.append(
            Finding(
                "laying_drop",
                level,
                {"hen_day_pct": round(today_pct, 1), "avg_7d_pct": round(avg, 1), "drop_pts": round(drop, 1)},
            )
        )
    return round(today_pct, 1), round(avg, 1), findings


def house_status(house: House, as_of: date, deaths_rule: DailyDeathsRule | None = None) -> HouseStatus:
    """``deaths_rule``: the farmer's own daily deaths rule, if he has one. It can only ADD a WATCH finding, so the
    house's level is max(what the rules above say, WATCH); no other finding, number or level reads it."""
    records = house.records_until(as_of)
    if not records:
        raise InsufficientData(f"the status of {house.label_en}", f"{house.label_te} స్థితి")
    latest = records[-1]
    if _live_at_start_of(house, latest.day) == 0:
        raise InsufficientData(
            f"the status of {house.label_en}, because no live birds are recorded there",
            f"{house.label_te} స్థితి (అక్కడ బతికి ఉన్న కోళ్లు నమోదు కాలేదు)",
        )
    findings: list[Finding] = []

    stale_days = (as_of - latest.day).days
    if stale_days > t.STALE_AFTER_DAYS:
        findings.append(
            Finding("records_stale", Level.WATCH, {"days_since_record": stale_days, "latest": latest.day.isoformat()})
        )
    findings += _mortality_findings(house, records, latest)
    if deaths_rule is not None:
        hit = evaluate_deaths_rule(deaths_rule, latest.deaths, _live_at_start_of(house, latest.day))
        if hit is not None:
            findings.append(
                Finding(
                    "daily_deaths_rule",
                    Level.WATCH,
                    {
                        "deaths": hit.deaths,
                        "live_at_start": hit.live_at_start,
                        "per_1000": hit.per_1000,
                        "limit_per_1000": hit.limit_per_1000,
                    },
                )
            )

    # A broiler breed without a cited curve still gets deaths, feed and weights; only target comparisons
    # are skipped, and the finding says so (never another breed's curve, Rule 6).
    has_curve = True
    if house.kind is HouseKind.BROILER:
        try:
            curve_for(house.breed)
        except NoReferenceCurve:
            has_curve = False
    if has_curve:
        feed_drop = _feed_drop_finding(house, records, latest)
        if feed_drop:
            findings.append(feed_drop)

    avg_w = w_day = target_w = farm_fcr = target_fcr = None
    hen_day = hen_day_avg = None
    if house.kind is HouseKind.BROILER and has_curve:
        avg_w, w_day, target_w, farm_fcr, target_fcr, growth_findings = _broiler_growth(house, records)
        findings += growth_findings
        max_day = curve_for(house.breed).max_day
        if house.age_days(as_of) > max_day:
            findings.append(Finding("past_growth_table", Level.OK, {"max_day": max_day}))
    elif house.kind is HouseKind.BROILER:
        weighed = [r for r in records if r.avg_weight_g is not None]
        if weighed:
            avg_w, w_day = weighed[-1].avg_weight_g, weighed[-1].day
        findings.append(Finding("no_reference_curve", Level.OK, {}))
    else:
        hen_day, hen_day_avg, lay_findings = _layer_production(house, records, latest)
        findings += lay_findings

    findings.sort(key=lambda f: f.level, reverse=True)
    live = house.live_birds(latest.day)
    return HouseStatus(
        house_id=house.house_id,
        label_en=house.label_en,
        label_te=house.label_te,
        kind=house.kind,
        breed=house.breed,
        as_of=as_of,
        latest_record_day=latest.day,
        age_days=house.age_days(as_of),
        birds_placed=house.birds_placed,
        live_birds=live,
        deaths_latest=latest.deaths,
        deaths_7d=sum(r.deaths for r in records if r.day > latest.day - timedelta(days=7)),
        cum_mortality_pct=round(100 * (house.birds_placed - live) / house.birds_placed, 2),
        feed_latest_kg=latest.feed_kg,
        feed_per_bird_latest_g=round(_per_bird_g(house, latest), 1),
        avg_weight_g=avg_w,
        weight_day=w_day,
        target_weight_g=target_w,
        farm_fcr=farm_fcr,
        target_fcr=target_fcr,
        hen_day_pct=hen_day,
        hen_day_pct_7d_avg=hen_day_avg,
        findings=tuple(findings),
    )
