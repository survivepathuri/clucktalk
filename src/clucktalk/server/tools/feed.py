"""``plan_feed``: feed needed over the next days, how long stock lasts, and whether to reorder (docs/DESIGN.md §5).

Planning only: nothing is ordered here (orders need propose -> "yes" -> confirm, docs/DESIGN.md §7 rule 4).
The feed price is simulated and said so in both languages. Same build order as get_farm_status:
domain plan -> rounded output model -> text rendered from the output model only.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from clucktalk.domain.errors import DomainError
from clucktalk.domain.feed import (
    BAG_KG,
    COVERAGE_LOOKAHEAD_DAYS,
    DEFAULT_HORIZON_DAYS,
    MAX_HORIZON_DAYS,
    MIN_HORIZON_DAYS,
    plan_feed,
)
from clucktalk.domain.houses import resolve_house
from clucktalk.domain.models import Farm, House
from clucktalk.domain.thresholds import STALE_AFTER_DAYS
from clucktalk.i18n import Text
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import num, plural, rupees, weekday_en, weekday_te
from clucktalk.server.tools import Capability, CapabilityRegistry, unavailable_text, whole_farm_or

MAX_SPOKEN_HOUSES = 5
WEEKDAY_WINDOW_DAYS = 6  # name the weekday only when it is unambiguous (within the coming week)
PHASE_TE = {"pre-starter": "ప్రీ-స్టార్టర్", "starter": "స్టార్టర్", "finisher": "ఫినిషర్"}


class DayNeedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: str
    age_days: int
    birds: int
    feed_kg: float


class PhaseChangeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: str
    in_days: int
    from_phase: str
    to_phase: str


class HouseFeedPlanOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    house_id: str
    number: int
    label_en: str
    label_te: str
    kind: Literal["broiler", "layer"]
    breed: str
    summary_en: str
    summary_te: str
    horizon_days: int
    days_since_record: int  # 0 = today's reading exists
    basis: Literal["house_actual", "breed_target_scaled", "breed_target"]
    need_kg: int
    stock_kg: int
    days_covered: int
    days_covered_is_minimum: bool
    runs_out_on: str | None
    reorder_needed: bool
    bag_kg: int
    suggested_order_bags: int
    suggested_order_kg: int
    feed_price_per_kg_inr: float
    suggested_order_cost_inr: int
    price_is_simulated: bool
    current_phase: str | None
    phase_change: PhaseChangeOut | None
    daily: list[DayNeedOut]


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


class FeedPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    as_of: str
    plans: list[HouseFeedPlanOut]
    unavailable: list[HouseUnavailableOut]


DESCRIPTION = (
    "Use when the farmer asks about feed (dana) for a house (shed, kotam) or the farm: how much is needed in the "
    "coming days, how long the stock lasts, whether to reorder, and when the broiler feed phase changes. Give "
    "`house` for one house (omit for every house) and optionally `horizon_days`. Plans only; it never places an "
    "order. Prices are simulated."
)
HOUSE_PARAM = Field(
    default=None,
    description=(
        "Which house. Accepts how farmers say it: 'shed 2', 'house two', 'kotam do', 'second shed', "
        "or a house_id such as 'house-2'. Omit (or say 'all') for every house."
    ),
)
HORIZON_PARAM = Field(
    default=DEFAULT_HORIZON_DAYS,
    ge=MIN_HORIZON_DAYS,
    le=MAX_HORIZON_DAYS,
    description=f"Days ahead to plan, {MIN_HORIZON_DAYS} to {MAX_HORIZON_DAYS}. Default {DEFAULT_HORIZON_DAYS}.",
)


def _cover(p: HouseFeedPlanOut, as_of: date) -> Text:
    """How long stock lasts, as a predicate: callers put their own subject before it."""
    d = p.days_covered
    if p.days_covered_is_minimum and d < COVERAGE_LOOKAHEAD_DAYS:
        # The projection stopped at the growth table's end, not because stock ran out.
        return Text(
            f"enough until the {p.breed} growth table ends in {d} {plural(d, 'day', 'days')}.",
            f"{p.breed} పెరుగుదల పట్టిక ముగిసే {d} రోజుల వరకు సరిపోతుంది.",
        )
    if p.days_covered_is_minimum:
        return Text(f"enough for at least {d} {plural(d, 'day', 'days')}.", f"కనీసం {d} రోజులు సరిపోతుంది.")
    if d == 0:
        return Text("not enough for tomorrow.", "రేపటికి సరిపోదు.")
    if d <= WEEKDAY_WINDOW_DAYS:
        last = as_of + timedelta(days=d)
        return Text(
            f"enough for about {d} {plural(d, 'day', 'days')}, until {weekday_en(last)}.",
            f"సుమారు {d} రోజులు, {weekday_te(last)} వరకు సరిపోతుంది.",
        )
    return Text(f"enough for about {d} days.", f"సుమారు {d} రోజులు సరిపోతుంది.")


def _order(p: HouseFeedPlanOut) -> Text:
    if not p.reorder_needed:
        return Text("No reorder needed yet.", "ఇంకా ఆర్డర్ అవసరం లేదు.")
    b = p.suggested_order_bags
    return Text(
        f"Order {b} {plural(b, 'bag', 'bags')} of {p.bag_kg} kg now: about {rupees(p.suggested_order_cost_inr)} "
        f"before GST and delivery, at the simulated price of {rupees(p.feed_price_per_kg_inr)} a kilo.",
        f"ఇప్పుడే {p.bag_kg} కిలోల {b} బస్తాలు ఆర్డర్ చేయండి: అంచనా ధర (డెమో) కిలోకు "
        f"{rupees(p.feed_price_per_kg_inr)} ప్రకారం సుమారు {rupees(p.suggested_order_cost_inr)} "
        "(జీఎస్‌టీ, డెలివరీ కాకుండా).",
    )


def _house_plan(farm: Farm, house: House, as_of: date, horizon_days: int) -> HouseFeedPlanOut:
    plan = plan_feed(farm, house, as_of, horizon_days)
    latest = house.records_until(as_of)[-1].day  # plan_feed refuses a house with no records
    change = None
    if plan.phase_change is not None:
        change = PhaseChangeOut(
            day=plan.phase_change.day.isoformat(),
            in_days=(plan.phase_change.day - as_of).days,
            from_phase=plan.phase_change.from_phase,
            to_phase=plan.phase_change.to_phase,
        )
    out = HouseFeedPlanOut(
        house_id=plan.house_id,
        number=house.number,
        label_en=plan.label_en,
        label_te=plan.label_te,
        kind=house.kind.value,
        breed=house.breed,
        summary_en="",
        summary_te="",
        horizon_days=plan.horizon_days,
        days_since_record=(as_of - latest).days,
        basis=plan.basis,
        need_kg=round(plan.need_kg),
        stock_kg=round(plan.stock_kg),
        days_covered=plan.days_covered,
        days_covered_is_minimum=plan.days_covered_capped,
        runs_out_on=None if plan.runs_out_on is None else plan.runs_out_on.isoformat(),
        reorder_needed=plan.reorder_needed,
        bag_kg=BAG_KG,
        suggested_order_bags=plan.suggested_order_bags,
        suggested_order_kg=plan.suggested_order_kg,
        feed_price_per_kg_inr=float(plan.feed_price_per_kg),
        suggested_order_cost_inr=int(plan.suggested_order_cost_inr),
        price_is_simulated=True,
        current_phase=plan.current_phase,
        phase_change=change,
        daily=[
            DayNeedOut(day=n.day.isoformat(), age_days=n.age_days, birds=n.birds, feed_kg=n.feed_kg) for n in plan.daily
        ],
    )
    cover = _cover(out, as_of)
    h = out.horizon_days
    need = (
        Text(f"tomorrow needs about {num(out.need_kg)} kg of feed.", f"రేపటికి సుమారు {num(out.need_kg)} కిలోల ఫీడ్ కావాలి.")
        if h == 1
        else Text(
            f"the next {h} days need about {num(out.need_kg)} kg of feed.",
            f"రాబోయే {h} రోజులకు సుమారు {num(out.need_kg)} కిలోల ఫీడ్ కావాలి.",
        )
    )
    parts = [
        Text(
            f"{out.label_en}: {need.en} You have {num(out.stock_kg)} kg, {cover.en}",
            f"{out.label_te}: {need.te} మీ దగ్గర {num(out.stock_kg)} కిలోలు ఉన్నాయి; ఇది {cover.te}",
        ),
        _order(out),
    ]
    if out.days_since_record > STALE_AFTER_DAYS:
        d = out.days_since_record
        parts.append(
            Text(
                f"My latest reading for {out.label_en} is {d} days old, so please check the stock count.",
                f"{out.label_te} తాజా రీడింగ్ {d} రోజుల క్రితం తీసుకున్నది, కాబట్టి దయచేసి నిల్వను ఒకసారి చూసుకోండి.",
            )
        )
    if change is not None:
        n = change.in_days
        parts.append(
            Text(
                f"Switch from {change.from_phase} to {change.to_phase} feed in {n} {plural(n, 'day', 'days')}.",
                f"{n} రోజుల్లో {PHASE_TE[change.from_phase]} ఫీడ్ నుండి {PHASE_TE[change.to_phase]} ఫీడ్‌కు మార్చండి.",
            )
        )
    if out.basis == "breed_target":
        parts.append(
            Text(
                f"This uses the {out.breed} standard because there are only a few records.",
                f"రికార్డులు తక్కువగా ఉన్నందున ఇది {out.breed} ప్రమాణం ఆధారంగా లెక్కించబడింది.",
            )
        )
    out.summary_en = " ".join(p.en for p in parts)
    out.summary_te = " ".join(p.te for p in parts)
    return out


def _short(p: HouseFeedPlanOut, as_of: date) -> Text:
    cover = _cover(p, as_of)
    head = Text(f"{p.label_en}: stock is {cover.en}", f"{p.label_te}: ఫీడ్ నిల్వ {cover.te}")
    if not p.reorder_needed:
        return head
    b = p.suggested_order_bags
    return Text(
        f"{head.en} Order {b} {plural(b, 'bag', 'bags')} now.",
        f"{head.te} ఇప్పుడే {b} బస్తాలు ఆర్డర్ చేయండి.",
    )


def build_plan(source: DemoFarmSource, house_ref: str | None, horizon_days: int) -> FeedPlanOutput:
    farm, as_of = source.snapshot()
    house_ref = whole_farm_or(house_ref)
    if house_ref is not None:
        out = _house_plan(farm, resolve_house(farm, house_ref), as_of, horizon_days)
        plans, unavailable = [out], []
        parts = [Text(out.summary_en, out.summary_te)]
    else:
        plans, unavailable = [], []
        for house in sorted(farm.houses, key=lambda h: h.number):
            try:
                plans.append(_house_plan(farm, house, as_of, horizon_days))
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
        plans.sort(key=lambda p: (not p.reorder_needed, p.days_covered, p.number))
        parts = [Text("Feed check for every house.", "అన్ని షెడ్ల ఫీడ్ తనిఖీ.")]
        items = [_short(p, as_of) for p in plans]
        items += [unavailable_text(u) for u in unavailable]
        parts += items[:MAX_SPOKEN_HOUSES]  # voice-only: at most 5 houses read out, planned or not
        if len(items) > MAX_SPOKEN_HOUSES:
            parts.append(
                Text("There are more houses; ask about one by shed number.", "ఇంకా షెడ్లు ఉన్నాయి; షెడ్ నంబర్ చెప్పి అడగండి.")
            )
        if any(p.reorder_needed for p in plans):
            parts.append(
                Text(
                    "Say a shed number to hear its full feed plan and the simulated cost.",
                    "పూర్తి ఫీడ్ ప్లాన్, అంచనా ధర (డెమో) కోసం షెడ్ నంబర్ చెప్పండి.",
                )
            )
    return FeedPlanOutput(
        text_en=" ".join(p.en for p in parts),
        text_te=" ".join(p.te for p in parts),
        demo_data=source.demo_data,
        as_of=as_of.isoformat(),
        plans=plans,
        unavailable=unavailable,
    )


def register(server: MCPServer, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    @server.tool(
        name="plan_feed",
        title="Feed plan",
        description=DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def plan_feed_tool(
        house: Annotated[str | None, HOUSE_PARAM] = None,
        horizon_days: Annotated[int, HORIZON_PARAM] = DEFAULT_HORIZON_DAYS,
    ) -> Annotated[CallToolResult, FeedPlanOutput]:
        try:
            out = build_plan(source, house, horizon_days)
        except DomainError as err:
            return domain_error_result(err)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name="plan_feed",
            title=Text("Feed stock and reorder", "ఫీడ్ నిల్వ, ఆర్డర్"),
            example_en="How much feed does shed two need this week?",
        )
    )
