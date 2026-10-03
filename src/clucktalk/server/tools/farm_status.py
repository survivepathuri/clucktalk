"""``get_farm_status``: how one house, or the whole farm, is doing today (docs/DESIGN.md §5, §6).

Build order enforces the cross-modal rule: domain status -> rounded output model -> text rendered from the
output model only (clucktalk.server.render). Telugu: review status per string in docs/TELUGU_REVIEW.md.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Literal

from mcp.server.apps import Apps
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from clucktalk.domain.briefing import Category
from clucktalk.domain.errors import DomainError
from clucktalk.domain.feed import plan_feed
from clucktalk.domain.houses import resolve_house
from clucktalk.domain.models import Farm, House, HouseKind
from clucktalk.domain.profile import FarmMode
from clucktalk.domain.status import Finding, Level, house_status
from clucktalk.domain.triage import Urgency
from clucktalk.i18n import Text
from clucktalk.server.cards import FARM_STATUS_URI, farm_status_html
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import num, plural
from clucktalk.server.tools import Capability, CapabilityRegistry, unavailable_text, whole_farm_or
from clucktalk.server.tools.follow_up import (
    FollowUpView,
    ShedHealth,
    check_said_text,
    follow_up_line,
    follow_up_view,
    shed_health,
    warns_vet,
)
from clucktalk.server.tools.safety import SafetyOut, fact_items, facts_for, item_needs_safety_step, status_safety

logger = logging.getLogger("clucktalk.server")

# Voice-only rule: at most 5 options or items read out (docs/DESIGN.md §6).
MAX_SPOKEN_HOUSES = 5
MAX_SPOKEN_FINDINGS = 3
LAYING_AVG_DAYS = 7  # the domain's laying baseline window, spoken as "7-day average"

LevelName = Literal["ok", "watch", "alert"]
_LEVEL_NAME: dict[Level, LevelName] = {Level.OK: "ok", Level.WATCH: "watch", Level.ALERT: "alert"}


class FindingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    level: LevelName
    text_en: str
    text_te: str
    values: dict[str, float]


class OpenCheckOut(BaseModel):
    """The shed's open health check when the status speaks it (a shed that is not OK says why): the numbers behind
    the sentence, so every spoken number is also here."""

    model_config = ConfigDict(extra="forbid")
    urgency: Literal["watch", "urgent", "notifiable_suspect"]  # the health check's own level
    days_ago: int
    ready: bool  # False while the check runs or after it failed: the level is then the code floor from the signs


class HouseStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    house_id: str
    number: int
    label_en: str
    label_te: str
    kind: Literal["broiler", "layer"]
    breed: str
    level: LevelName
    summary_en: str
    summary_te: str
    latest_record_day: str
    age_days: int
    birds_placed: int
    live_birds: int
    deaths_latest: int
    deaths_7d: int
    cum_mortality_pct: float
    feed_latest_kg: int
    feed_per_bird_g: int
    avg_weight_g: int | None
    target_weight_g: int | None
    farm_fcr: float | None
    target_fcr: float | None
    hen_day_pct: float | None
    hen_day_pct_7d_avg: float | None
    feed_days_covered: int | None
    feed_days_covered_is_minimum: bool | None  # None when cover is unknown
    findings: list[FindingOut]
    follow_up: FollowUpView | None = None  # this shed's follow-up after a health check, if it has one
    open_health_check: OpenCheckOut | None = None  # the open check spoken for this shed, when there is one


class HouseUnavailableOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    house_id: str
    number: int
    label_en: str
    label_te: str
    breed: str
    message_en: str
    message_te: str
    values: dict[str, float]


class FarmStatusOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    as_of: str
    level: LevelName | Literal["unknown"]  # "unknown" when no house could be checked (never a silent "ok")
    houses: list[HouseStatusOut]
    unavailable: list[HouseUnavailableOut]
    safety: SafetyOut  # the structured safety step: level = the card level, why, and whether to contact the vet


DESCRIPTION = (
    "Use when the farmer asks how a house (shed, kotam) or the whole farm is doing right now: deaths, feed intake, "
    "weight vs breed target, whether feed stock is running low, and any open health check or follow-up for that "
    "house. Give `house` for one house; omit it for every house, worst first. Not for today's priorities across the "
    "farm (use get_daily_briefing) and not for reporting new signs (use start_health_check). Returns a short spoken "
    "summary plus the same numbers for the card."
)
HOUSE_PARAM = Field(
    default=None,
    description=(
        "Which house. Accepts how farmers say it: 'shed 2', 'house two', 'kotam do', 'second shed', "
        "or a house_id such as 'house-2'. Omit (or say 'all') for the whole farm."
    ),
)


def _level_sentence(h: HouseStatusOut) -> Text:
    return {
        "ok": Text(f"{h.label_en} is doing well.", f"{h.label_te} బాగుంది."),
        "watch": Text(f"{h.label_en} needs a closer look.", f"{h.label_te} ని కొంచెం గమనించాలి."),
        "alert": Text(f"{h.label_en} needs attention now.", f"{h.label_te} కి వెంటనే శ్రద్ధ అవసరం."),
    }[h.level]


def _finding(f: Finding, breed: str, is_today: bool) -> FindingOut:
    v = f.values
    level = _LEVEL_NAME[f.level]
    match f.code:
        case "records_stale":
            d = int(v["days_since_record"])
            vals = {"days_since_record": d}
            en = f"No readings for {d} {plural(d, 'day', 'days')}."
            te = f"{d} రోజులుగా రీడింగులు లేవు."
        case "cum_mortality_high":
            pct = round(float(v["cum_mortality_pct"]), 1)
            vals = {"cum_mortality_pct": pct}
            en = f"Total losses are {num(pct)}% of the birds placed."
            te = f"వేసిన కోళ్లలో మొత్తం {num(pct)}% చనిపోయాయి."
        case "mortality_spike":
            deaths, base = int(v["deaths"]), round(float(v["baseline_daily_avg"]))
            vals = {"deaths": deaths, "baseline_per_day": base}
            when = _when(is_today)
            if base == 0:
                en = f"{num(deaths)} birds died {when.en}, after hardly any deaths this past week."
                te = f"{when.te} {num(deaths)} కోళ్లు చనిపోయాయి; గత వారం దాదాపు ఏవీ చనిపోలేదు."
            else:
                en = f"{num(deaths)} birds died {when.en}, against about {num(base)} a day this past week."
                te = f"{when.te} {num(deaths)} కోళ్లు చనిపోయాయి; గత వారం రోజుకు సుమారు {num(base)}."
        case "feed_intake_drop":
            got, exp, drop = (
                round(float(v["per_bird_g"])),
                round(float(v["expected_per_bird_g"])),
                round(float(v["drop_pct"])),
            )
            vals = {"per_bird_g": got, "expected_per_bird_g": exp, "drop_pct": drop}
            en = f"Birds ate {drop}% less than expected: {got} g per bird against {exp} g."
            te = f"కోళ్లు అంచనా కంటే {drop}% తక్కువ తిన్నాయి: ఒక్కో కోడికి {got} గ్రా., అంచనా {exp} గ్రా."
        case "weight_below_target":
            w, tgt, pct = (
                round(float(v["avg_weight_g"])),
                round(float(v["target_weight_g"])),
                round(float(v["pct_of_target"])),
            )
            vals = {"avg_weight_g": w, "target_weight_g": tgt, "pct_of_target": pct}
            en = f"Average weight is {num(w)} g, {pct}% of the {breed} target of {num(tgt)} g."
            te = f"సగటు బరువు {num(w)} గ్రా., {breed} లక్ష్యం {num(tgt)} గ్రా.లో {pct}%."
        case "fcr_above_target":
            fcr, tgt = round(float(v["farm_fcr"]), 2), round(float(v["target_fcr"]), 2)
            vals = {"farm_fcr": fcr, "target_fcr": tgt}
            en = f"Feed conversion is {num(fcr)}, above the target of {num(tgt)}."
            te = f"FCR {num(fcr)}, లక్ష్యం {num(tgt)} కంటే ఎక్కువ."
        case "laying_drop":
            pct, avg = round(float(v["hen_day_pct"]), 1), round(float(v["avg_7d_pct"]), 1)
            drop = round(avg - pct, 1)  # from the rounded values, so the spoken arithmetic adds up
            vals = {"hen_day_pct": pct, "avg_pct": avg, "drop_pts": drop, "avg_days": LAYING_AVG_DAYS}
            when = _when(is_today)
            en = (
                f"Laying is {num(pct)}% {when.en}, down {num(drop)} points "
                f"from the {LAYING_AVG_DAYS}-day average of {num(avg)}%."
            )
            te = (
                f"{when.te} గుడ్ల ఉత్పత్తి {num(pct)}%, {LAYING_AVG_DAYS} రోజుల సగటు {num(avg)}% కంటే "
                f"{num(drop)} పాయింట్లు తక్కువ."
            )
        case "past_growth_table":
            md = int(v["max_day"])
            vals = {"max_day": md}
            en = f"The flock is past day {md} of the {breed} growth table, so weight is not compared to a target."
            te = f"బ్యాచ్ {breed} పెరుగుదల పట్టికలోని {md}వ రోజు దాటింది, కాబట్టి బరువును లక్ష్యంతో పోల్చలేదు."
        case "no_reference_curve":
            vals = {}
            en = f"I have no verified {breed} growth standard, so weight and feed are not compared to a target."
            te = f"{breed} కి ధృవీకరించిన పెరుగుదల ప్రమాణం లేదు, కాబట్టి బరువు, ఫీడ్‌ను లక్ష్యంతో పోల్చలేదు."
        case _:
            raise ValueError(f"no wording for finding {f.code!r}")  # a new finding must get wording first
    return FindingOut(code=f.code, level=level, text_en=en, text_te=te, values=vals)


def _when(is_today: bool) -> Text:
    """'today' only when the latest record is from today; otherwise say it is the latest count."""
    return Text("today", "ఈరోజు") if is_today else Text("in the latest count", "తాజా లెక్కలో")


def _feed_stock_finding(days: int, stock_kg: float) -> FindingOut:
    if stock_kg <= 0:
        en, te = "There is no feed stock left.", "ఫీడ్ నిల్వ అయిపోయింది."
    elif days == 0:
        en, te = "Feed stock runs out by tomorrow.", "ఫీడ్ నిల్వ రేపటికే అయిపోతుంది."
    else:
        en = f"Feed stock lasts about {days} {plural(days, 'day', 'days')}."
        te = f"ఫీడ్ నిల్వ సుమారు {days} రోజులు సరిపోతుంది."
    return FindingOut(code="feed_stock_low", level="watch", text_en=en, text_te=te, values={"days_covered": days})


def _house_out(farm: Farm, house: House, as_of, floor: LevelName = "ok") -> HouseStatusOut:
    """``floor``: the level the shed's open health check or follow-up asks for; the shed is never shown lower."""
    st = house_status(house, as_of)
    is_today = st.latest_record_day == as_of
    findings = [_finding(f, st.breed, is_today) for f in st.findings]

    days_covered, is_min = None, None
    try:
        plan = plan_feed(farm, house, as_of)
        days_covered, is_min = plan.days_covered, plan.days_covered_capped
        if plan.reorder_needed:
            findings.append(_feed_stock_finding(plan.days_covered, plan.stock_kg))
    except DomainError as err:
        # Stock cover is optional detail in a status answer; the card shows it as unknown (None), and
        # plan_feed gives the farmer the reason when asked directly.
        logger.info("status for %s: feed cover unavailable (%s)", house.house_id, err.customer_message)
    order = {"alert": 0, "watch": 1, "ok": 2}
    findings.sort(key=lambda f: order[f.level])
    level: LevelName = min((*(f.level for f in findings), floor), key=lambda lv: order[lv])

    avg_w = None if st.avg_weight_g is None else round(st.avg_weight_g)
    tgt_w = None if st.target_weight_g is None else round(st.target_weight_g)
    hen_day = None if st.hen_day_pct is None else round(st.hen_day_pct, 1)
    out = HouseStatusOut(
        house_id=st.house_id,
        number=house.number,
        label_en=st.label_en,
        label_te=st.label_te,
        kind=st.kind.value,
        breed=st.breed,
        level=level,
        summary_en="",
        summary_te="",
        latest_record_day=st.latest_record_day.isoformat(),
        age_days=st.age_days,
        birds_placed=st.birds_placed,
        live_birds=st.live_birds,
        deaths_latest=st.deaths_latest,
        deaths_7d=st.deaths_7d,
        cum_mortality_pct=round(st.cum_mortality_pct, 1),
        feed_latest_kg=round(st.feed_latest_kg),
        feed_per_bird_g=round(st.feed_per_bird_latest_g),
        avg_weight_g=avg_w,
        target_weight_g=tgt_w,
        farm_fcr=None if st.farm_fcr is None else round(st.farm_fcr, 2),
        target_fcr=None if st.target_fcr is None else round(st.target_fcr, 2),
        hen_day_pct=hen_day,
        hen_day_pct_7d_avg=None if st.hen_day_pct_7d_avg is None else round(st.hen_day_pct_7d_avg, 1),
        feed_days_covered=days_covered,
        feed_days_covered_is_minimum=is_min,
        findings=findings,
    )
    head = _level_sentence(out)
    if house.kind is HouseKind.BROILER:
        detail_en = f"Day {out.age_days}, {num(out.live_birds)} birds"
        detail_te = f"{out.age_days}వ రోజు, {num(out.live_birds)} కోళ్లు"
        if avg_w is not None and tgt_w is not None:
            detail_en += f", average weight {num(avg_w)} g against the {out.breed} target of {num(tgt_w)} g"
            detail_te += f", సగటు బరువు {num(avg_w)} గ్రా. ({out.breed} లక్ష్యం {num(tgt_w)} గ్రా.)"
        elif avg_w is not None:
            detail_en += f", average weight {num(avg_w)} g"
            detail_te += f", సగటు బరువు {num(avg_w)} గ్రా."
    else:
        detail_en = f"{num(out.live_birds)} birds"
        detail_te = f"{num(out.live_birds)} కోళ్లు"
        if hen_day is not None:
            when = _when(is_today)
            detail_en += f", laying {num(hen_day)}% {when.en}"
            detail_te += f", {when.te} గుడ్ల ఉత్పత్తి {num(hen_day)}%"
    out.summary_en = f"{head.en} {detail_en}."
    out.summary_te = f"{head.te} {detail_te}."
    return out


SAFETY_STEP = Text(
    "Please check the birds today and call your vet if deaths continue.",
    "దయచేసి ఈరోజే కోళ్లను పరిశీలించండి, మరణాలు కొనసాగితే మీ డాక్టర్‌కి ఫోన్ చేయండి.",
)
FEED_PLAN_HINT = Text(
    "Ask me for a feed plan to hear how much to order.",
    "ఎంత ఆర్డర్ చేయాలో తెలుసుకోవడానికి నన్ను ఫీడ్ ప్లాన్ అడగండి.",
)
FEED_PLAN_HINT_CONTRACT = Text(  # contract farm: the company supplies feed (docs/DESIGN.md §13.1)
    "Ask me for a feed plan to hear how much feed to ask your supervisor for.",
    "సూపర్‌వైజర్‌ని ఎంత ఫీడ్ అడగాలో తెలుసుకోవడానికి నన్ను ఫీడ్ ప్లాన్ అడగండి.",
)


def _closing(spoken: list[FindingOut], contract: bool, vet_line: bool = False) -> list[Text]:
    """Follow-up steps only for findings that were actually read out. ``vet_line``: a shed read out has an urgent
    check or a suspected reportable disease (open, or carried by its follow-up): the same vet step as a death spike."""
    codes = {f.code for f in spoken}
    extra = []
    if "mortality_spike" in codes or vet_line:
        extra.append(SAFETY_STEP)
    if "feed_stock_low" in codes:
        extra.append(FEED_PLAN_HINT_CONTRACT if contract else FEED_PLAN_HINT)
    return extra


_FACT_LEVEL: dict[Level, LevelName] = {Level.ALERT: "alert", Level.WATCH: "watch", Level.OK: "ok"}


def _health_floor(health: ShedHealth) -> LevelName:
    """The level the shed's open health check or follow-up asks for: the briefing's own level for its health item
    (urgent or reportable: alert; watch: watch; escalated follow-up: alert; due follow-up: at least watch)."""
    return "ok" if health.fact is None else _FACT_LEVEL[health.fact.level]


def _attach_health(house: House, as_of: date, health: ShedHealth, out: HouseStatusOut) -> Text | None:
    """Put the shed's follow-up (if it has one) on its status, and return the one sentence spoken for its health: the
    follow-up question or escalation, the open check's own sentence (so a shed that is not OK says why), or a lapsed
    follow-up's "no answer"."""
    label = Text(house.label_en, house.label_te)
    fup = health.follow_up
    if fup is not None:
        out.follow_up = follow_up_view(fup, label, as_of)
    fact = health.fact
    if fact is not None and fact.category is Category.OPEN_HEALTH_CHECK:
        urgency = next(u for u in Urgency if u.code == fact.values["urgency"])
        days, ready = int(fact.values["days_ago"]), bool(fact.values["ready"])
        out.open_health_check = OpenCheckOut(urgency=urgency.code, days_ago=days, ready=ready)  # type: ignore[arg-type]
        return check_said_text(label, urgency, days, ready)
    return None if fup is None else follow_up_line(fup, label, as_of)


def _needs_vet_line(health: ShedHealth) -> bool:
    """An urgent check or a suspected reportable disease (open, or carried by its follow-up): the vet closing line."""
    fact = health.fact
    return fact is not None and warns_vet(next(u for u in Urgency if u.code == fact.values["urgency"]))


def build_status(source: DemoFarmSource, house_ref: str | None) -> FarmStatusOutput:
    farm, as_of = source.snapshot()
    order = {"alert": 0, "watch": 1, "ok": 2}
    house_ref = whole_farm_or(house_ref)
    follow_up_lines: dict[str, Text] = {}
    vet_houses: set[str] = set()
    scope: list[House] | None = None  # the sheds the safety field reads: the one asked about, else the whole farm
    if house_ref is not None:
        house = resolve_house(farm, house_ref)
        scope = [house]
        health = shed_health(source, farm.farm_id, house, as_of)
        # A DomainError propagates here: the one shed asked about failed.
        out = _house_out(farm, house, as_of, _health_floor(health))
        houses, unavailable = [out], []
        spoken = out.findings[:MAX_SPOKEN_FINDINGS]
        parts = [Text(out.summary_en, out.summary_te)] + [Text(f.text_en, f.text_te) for f in spoken]
        line = _attach_health(house, as_of, health, out)
        if line is not None:
            parts.append(line)
        if _needs_vet_line(health):
            vet_houses.add(house.house_id)
    else:
        houses, unavailable = [], []
        for house in sorted(farm.houses, key=lambda h: h.number):
            try:
                health = shed_health(source, farm.farm_id, house, as_of)
                out = _house_out(farm, house, as_of, _health_floor(health))
                line = _attach_health(house, as_of, health, out)
                if line is not None:
                    follow_up_lines[house.house_id] = line
                if _needs_vet_line(health):
                    vet_houses.add(house.house_id)
                houses.append(out)
            except DomainError as err:
                unavailable.append(
                    HouseUnavailableOut(
                        house_id=house.house_id,
                        number=house.number,
                        label_en=house.label_en,
                        label_te=house.label_te,
                        breed=house.breed,
                        message_en=err.customer_message,
                        message_te=err.customer_message_te,
                        values=err.values,
                    )
                )
        houses.sort(key=lambda h: (order[h.level], h.number))
        parts = [Text("Here's your farm today.", "ఈరోజు మీ ఫారం స్థితి.")]
        items: list[Text] = []
        spoken = []
        for h in houses:
            head = _level_sentence(h)
            line = follow_up_lines.get(h.house_id)  # the one spoken health sentence this shed has, if any
            tail = Text(f" {line.en}", f" {line.te}") if line is not None else Text("", "")
            if not h.findings:
                items.append(Text(head.en + tail.en, head.te + tail.te))
                continue
            if len(items) < MAX_SPOKEN_HOUSES:
                spoken.append(h.findings[0])
            items.append(
                Text(f"{head.en} {h.findings[0].text_en}{tail.en}", f"{head.te} {h.findings[0].text_te}{tail.te}")
            )
        items += [unavailable_text(u) for u in unavailable]
        parts += items[:MAX_SPOKEN_HOUSES]  # voice-only: at most 5 houses read out, checked or not
        if len(items) > MAX_SPOKEN_HOUSES:
            parts.append(
                Text("There are more houses; ask about one by shed number.", "ఇంకా షెడ్లు ఉన్నాయి; షెడ్ నంబర్ చెప్పి అడగండి.")
            )
        vet_houses &= {h.house_id for h in houses[:MAX_SPOKEN_HOUSES]}  # only the sheds actually read out
    parts += _closing(spoken, source.profile().mode is FarmMode.CONTRACT, bool(vet_houses))
    level = min((h.level for h in houses), key=lambda lv: order[lv], default="unknown")
    if unavailable and level == "ok":
        level = "watch"  # some houses could not be checked: not everything is known to be fine
    return FarmStatusOutput(
        text_en=" ".join(p.en for p in parts),
        text_te=" ".join(p.te for p in parts),
        demo_data=source.demo_data,
        as_of=as_of.isoformat(),
        level=level,
        houses=houses,
        unavailable=unavailable,
        safety=status_safety(level, fact_items(facts_for(source, farm, as_of, scope)), item_needs_safety_step),
    )


def register(apps: Apps, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    """Registered through the MCP Apps extension: the tool's ``_meta.ui.resourceUri`` names the card, and hosts
    without MCP Apps still get the full spoken answer in ``content`` (spec: graceful degradation)."""
    card = farm_status_html().replace('"@SERVER_DEMO@"', "true" if source.demo_data else "false")
    apps.add_html_resource(
        FARM_STATUS_URI,
        card,
        name="farm-status-card",
        title="Farm status card",
        description="Bilingual (Telugu + English) card for get_farm_status: one shed or the whole farm.",
        prefers_border=False,
    )

    @apps.tool(
        resource_uri=FARM_STATUS_URI,
        name="get_farm_status",
        title="Farm status",
        description=DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def get_farm_status(
        house: Annotated[str | None, HOUSE_PARAM] = None,
    ) -> Annotated[CallToolResult, FarmStatusOutput]:
        try:
            out = build_status(source, house)
        except DomainError as err:
            return domain_error_result(err)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name="get_farm_status",
            title=Text("How a shed is doing", "షెడ్ ఎలా ఉందో"),
            example_en="How is shed two doing?",
        )
    )
