"""``plan_sale``: when to sell a broiler shed (docs/DESIGN.md §12.4, the hero feature).

Independent farmers: for each day from today to +10, the value of the weight gained minus the feed eaten minus
expected mortality loss, at a simulated (or farmer-given) live-bird price. Says the best day, the break-even day
(the first day an extra day stops paying for itself), and ₹ for today vs the best day vs a later day.
Contract farmers get no market-price advice (they aren't paid the open-market rate): instead the same per-day
weight/feed/mortality numbers show how FCR rises, and -- once the farmer has saved contract terms
(set_contract_terms) -- the growing charge, as evidence for asking the company to lift the birds on time.
Same build order as the other tools: domain plan -> rounded output model -> text rendered from the output only.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from mcp.server.apps import Apps
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from clucktalk.domain.errors import DomainError, NoReferenceCurve
from clucktalk.domain.houses import resolve_house
from clucktalk.domain.models import Farm, House, HouseKind
from clucktalk.domain.profile import ContractTerms, FarmMode
from clucktalk.domain.sale import DayOutcome, SalePlan, plan_sale
from clucktalk.i18n import Text
from clucktalk.pilot import is_unmodelled_breed
from clucktalk.server.cards import SALE_PLAN_URI, sale_plan_html
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import num, rupees, weekday_en, weekday_te
from clucktalk.server.tools import Capability, CapabilityRegistry, unavailable_text, whole_farm_or

MAX_SPOKEN_DAYS = 3  # the farmer's own limit for this feature: today, the best day, and the break-even day
MAX_SPOKEN_HOUSES = 5  # voice-only rule: at most 5 options (docs/DESIGN.md §6)

logger = logging.getLogger("clucktalk.server")


class DayOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: str
    weekday_en: str
    weekday_te: str
    in_days: int  # 0 = today
    age_days: int
    live_birds: int
    weight_g: int
    weight_gain_g: int
    feed_kg: int
    fcr: float | None
    # None in contract mode (docs/DESIGN.md §12.4 rule): a contract farmer is never shown a market-price number,
    # so these are never computed for that mode, even unread (Rule 6: never a hidden, misleading figure).
    gain_value_inr: int | None
    feed_cost_inr: int | None
    mortality_loss_inr: int | None
    marginal_profit_inr: int | None
    net_vs_today_inr: int | None
    growing_charge_inr: int | None  # contract mode, once terms are saved: the flock's value that day
    rate_per_kg_inr: float | None  # contract mode: the terms' rate at that day's FCR


class HouseSaleOut(BaseModel):
    """One house's plan. Always nested under PlanSaleOutput.plans (even a single-house query is a list of one),
    so the tool has exactly one output schema (docs/DESIGN.md §5 rule 3), the same pattern get_farm_status and
    plan_feed use."""

    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    house_id: str
    number: int
    label_en: str
    label_te: str
    breed: str
    as_of: str
    farm_mode: Literal["contract", "independent"]
    weight_basis: Literal["house_actual", "breed_target"]
    live_price_per_kg_inr: float | None  # independent mode only
    price_is_simulated: bool
    feed_price_per_kg_inr: float | None  # independent mode only: a contract farmer doesn't buy this feed
    mortality_rate_pct: float
    mortality_rising: bool
    has_contract_terms: bool  # contract mode only
    days: list[DayOut]
    best_day_index: int | None  # None in contract mode: "best" is a market-price notion
    break_even_day_index: int | None


class HouseUnavailableOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    house_id: str
    number: int
    label_en: str
    label_te: str
    message_en: str
    message_te: str
    values: dict[str, float]


class PlanSaleOutput(BaseModel):
    """The tool's one output shape. A single house: plans has one item, and the top text is that house's own
    text. The whole farm: plans holds every broiler shed (worst break-even first), unavailable any that failed."""

    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    as_of: str
    farm_mode: Literal["contract", "independent"]
    plans: list[HouseSaleOut]
    unavailable: list[HouseUnavailableOut]


DESCRIPTION = (
    "Use when the farmer asks when to sell a broiler shed, whether to wait, or about the best day, break-even day "
    "or growing charge for selling. Give `house` for one house (omit for every broiler shed on the farm) and "
    "optionally `live_price_per_kg` when the farmer states today's rate. Independent farms: the best day to sell "
    "and the ₹ difference. The market price is a simulated value from a simulated feed, not a real market quote; a "
    'rate the farmer states with `live_price_per_kg` is used as given, and the result text says "Simulated" '
    "whenever it uses the simulated price. Contract farms: no market price is used; instead how FCR and the "
    "growing charge change with each extra day. Not for layer flocks (ask get_farm_status or plan_feed instead)."
)
HOUSE_PARAM = Field(
    default=None,
    description=(
        "Which broiler house. Accepts 'shed 2', 'house two', 'kotam do', 'second shed', or a house_id. "
        "Omit for every broiler shed."
    ),
)
PRICE_PARAM = Field(
    default=None,
    gt=0,
    description="Today's live-bird rate in rupees per kg, if the farmer states it. Independent mode only.",
)


def _day_out(d: DayOutcome, as_of: date, terms: ContractTerms | None, *, market: bool) -> DayOut:
    """``market=False`` (contract mode): never carry a market-price-derived ₹ number, even unread -- a contract
    farmer isn't paid the open-market rate, so plan_sale's own domain math (which always prices against the
    farm's simulated or given rate) must not leak into this mode's output (independent review, 2026-09-29)."""
    charge = rate = None
    if terms is not None and d.fcr is not None:
        r = terms.rate_per_kg(Decimal(str(d.fcr)))
        charge = round(float(Decimal(str(d.live_birds)) * Decimal(str(d.weight_g / 1000)) * r))
        rate = round(float(r), 2)
    return DayOut(
        day=d.day.isoformat(),
        weekday_en=weekday_en(d.day),
        weekday_te=weekday_te(d.day),
        in_days=(d.day - as_of).days,
        age_days=d.age_days,
        live_birds=d.live_birds,
        weight_g=round(d.weight_g),
        weight_gain_g=round(d.weight_gain_g),
        feed_kg=round(d.feed_kg),
        fcr=d.fcr,
        gain_value_inr=int(d.gain_value_inr) if market else None,
        feed_cost_inr=int(d.feed_cost_inr) if market else None,
        mortality_loss_inr=int(d.mortality_loss_inr) if market else None,
        marginal_profit_inr=int(d.marginal_profit_inr) if market else None,
        net_vs_today_inr=int(d.net_vs_today_inr) if market else None,
        growing_charge_inr=charge,
        rate_per_kg_inr=rate,
    )


def _day_label(d: DayOut) -> Text:
    if d.in_days == 0:
        return Text("today", "ఈరోజు")
    if d.in_days == 1:
        return Text("tomorrow", "రేపు")
    return Text(f"{d.weekday_en} ({d.in_days} days from now)", f"{d.weekday_te} ({d.in_days} రోజుల్లో)")


def _independent_summary(out: HouseSaleOut) -> Text:
    best = out.days[out.best_day_index]
    if out.best_day_index == 0:
        head = Text(
            f"{out.label_en}: selling today is best. Each extra day would lose value.",
            f"{out.label_te}: ఈరోజే అమ్మడం మంచిది. ప్రతి అదనపు రోజు నష్టమే.",
        )
    else:
        lab = _day_label(best)
        diff = best.net_vs_today_inr
        head = Text(
            f"{out.label_en}: best to sell {lab.en}, about {rupees(diff)} more than selling today.",
            f"{out.label_te}: {lab.te} అమ్మడం మంచిది, ఈరోజు అమ్మడం కంటే సుమారు {rupees(diff)} ఎక్కువ.",
        )
    if out.break_even_day_index is not None:
        be = out.days[out.break_even_day_index]
        lab = _day_label(be)
        head = Text(
            f"{head.en} From {lab.en}, one more day starts to cost more feed than the weight it adds.",
            f"{head.te} {lab.te} నుండి, ఒక్క రోజు ఎక్కువగా ఉంచితే అది జోడించే బరువు కంటే ఫీడ్ ఖర్చు ఎక్కువవుతుంది.",
        )
    spoken_days = sorted({0, out.best_day_index})
    if out.break_even_day_index is not None:
        spoken_days.append(out.break_even_day_index)
    spoken_days = sorted(set(spoken_days))[:MAX_SPOKEN_DAYS]
    lines: list[Text] = []
    for i in spoken_days:
        d = out.days[i]
        lab = _day_label(d)
        lines.append(
            Text(
                f"{lab.en}: {num(d.weight_g)} g, net {rupees(d.net_vs_today_inr)} vs today",
                f"{lab.te}: {num(d.weight_g)} గ్రా., ఈరోజుతో పోలిస్తే నికరం {rupees(d.net_vs_today_inr)}",
            )
        )
    detail = Text(" ".join(t.en for t in lines), " ".join(t.te for t in lines))
    price_note = Text(
        f"Simulated price {rupees(out.live_price_per_kg_inr)} per kg; say today's rate to use it instead.",
        f"అంచనా ధర (డెమో) కిలోకు {rupees(out.live_price_per_kg_inr)}; బదులుగా ఈరోజు రేటు చెప్పండి.",
    )
    return Text(f"{head.en} {detail.en} {price_note.en}", f"{head.te} {detail.te} {price_note.te}")


def _contract_summary(out: HouseSaleOut) -> Text:
    today, later = out.days[0], out.days[min(3, len(out.days) - 1)]
    fcr_line = Text(
        f"{out.label_en}: FCR is about {today.fcr} today; keeping the birds longer raises it "
        f"(about {later.fcr} by {_day_label(later).en}).",
        f"{out.label_te}: ఈరోజు FCR సుమారు {today.fcr}; కోళ్లను ఎక్కువ రోజులు ఉంచితే అది పెరుగుతుంది "
        f"({_day_label(later).te} నాటికి సుమారు {later.fcr}).",
    )
    if not out.has_contract_terms:
        hint = Text(
            "Say set_contract_terms with your rate to see how this changes your growing charge.",
            "మీ గ్రోయింగ్ ఛార్జ్ ఎలా మారుతుందో చూడాలంటే మీ కాంట్రాక్ట్ నిబంధనలు చెప్పండి.",
        )
        return Text(f"{fcr_line.en} {hint.en}", f"{fcr_line.te} {hint.te}")
    charge_today, charge_later = today.growing_charge_inr, later.growing_charge_inr
    charge_line = Text(
        f"Your growing charge today is about {rupees(charge_today)}; by {_day_label(later).en} it would be "
        f"about {rupees(charge_later)}, based on your own terms.",
        f"ఈరోజు మీ గ్రోయింగ్ ఛార్జ్ సుమారు {rupees(charge_today)}; {_day_label(later).te} నాటికి మీ నిబంధనల ప్రకారం "
        f"సుమారు {rupees(charge_later)} అవుతుంది.",
    )
    ask = Text(
        "Show this to your supervisor to ask for the birds to be lifted on time.",
        "కోళ్లను సకాలంలో తీసుకెళ్లమని మీ సూపర్‌వైజర్‌ని అడగడానికి ఇది చూపించండి.",
    )
    return Text(f"{fcr_line.en} {charge_line.en} {ask.en}", f"{fcr_line.te} {charge_line.te} {ask.te}")


def _house_plan(
    farm: Farm, house: House, as_of: date, mode: FarmMode, price: Decimal | None, terms: ContractTerms | None
) -> HouseSaleOut:
    market = mode is FarmMode.INDEPENDENT
    plan: SalePlan = plan_sale(farm, house, as_of, price if market else None)
    days = [_day_out(d, as_of, terms if not market else None, market=market) for d in plan.days]
    out = HouseSaleOut(
        text_en="",
        text_te="",
        demo_data=True,
        house_id=house.house_id,
        number=house.number,
        label_en=house.label_en,
        label_te=house.label_te,
        breed=house.breed,
        as_of=as_of.isoformat(),
        farm_mode=mode.value,
        weight_basis=plan.weight_basis,
        live_price_per_kg_inr=float(plan.live_price_per_kg) if market else None,
        price_is_simulated=(price is None),
        feed_price_per_kg_inr=float(plan.feed_price_per_kg) if market else None,
        mortality_rate_pct=plan.mortality_rate_pct,
        mortality_rising=plan.mortality_rising,
        has_contract_terms=terms is not None,
        days=days,
        best_day_index=plan.best_day_index if market else None,
        break_even_day_index=plan.break_even_day_index if market else None,
    )
    summary = _independent_summary(out) if mode is FarmMode.INDEPENDENT else _contract_summary(out)
    out.text_en, out.text_te = summary.en, summary.te
    return out


def _unmodelled_text(source: DemoFarmSource, paper: Decimal | None) -> Text:
    """A pilot house with no growth standard has no sale plan. With the farmer's own rule (price = paper rate minus a
    fixed amount) the answer is his price, or one ask for the rate; never a made-up rate. Without the rule, one plain
    line. The technical reason stays in the logs, not in what the farmer reads."""
    delta = source.paper_rate_delta
    if delta is None:
        return Text("Sale planning is not part of this pilot yet.", "ఈ పైలట్ లో అమ్మకం లెక్క ఇంకా లేదు.")
    if paper is None or paper <= delta:
        return Text(
            "Tell me today's paper rate and I will work out your price.",
            "ఈరోజు పేపర్ రేటు చెప్పండి, మీ ధర నేను లెక్కిస్తాను.",
        )
    return Text(
        f"Your price today: {rupees(paper - delta)} per kg (paper rate {rupees(paper)} minus {rupees(delta)}, "
        "your own rule).",
        f"మీ ఈరోజు ధర: కిలోకు {rupees(paper - delta)} (పేపర్ రేటు {rupees(paper)} నుండి {rupees(delta)} తగ్గింపు, మీ సొంత నియమం).",
    )


def build_plan(source: DemoFarmSource, house_ref: str | None, live_price_per_kg: float | None) -> PlanSaleOutput:
    farm, as_of = source.snapshot()
    mode = source.profile().mode
    terms = source.store.get_contract_terms(source.farm_id) if mode is FarmMode.CONTRACT else None
    price = Decimal(str(live_price_per_kg)) if live_price_per_kg is not None else None

    house_ref = whole_farm_or(house_ref)
    if house_ref is not None:
        house = resolve_house(farm, house_ref)
        try:
            out = _house_plan(farm, house, as_of, mode, price, terms)  # DomainError propagates: the one house asked
        except NoReferenceCurve as err:
            if not is_unmodelled_breed(house.breed):
                raise
            logger.info("sale for %s: no growth standard (%s)", house.house_id, err.customer_message)
            quiet = _unmodelled_text(source, price)
            return PlanSaleOutput(
                text_en=quiet.en,
                text_te=quiet.te,
                demo_data=source.demo_data,
                as_of=as_of.isoformat(),
                farm_mode=mode.value,
                plans=[],
                unavailable=[],
            )
        return PlanSaleOutput(
            text_en=out.text_en,
            text_te=out.text_te,
            demo_data=True,
            as_of=as_of.isoformat(),
            farm_mode=mode.value,
            plans=[out],
            unavailable=[],
        )

    broilers = sorted((h for h in farm.houses if h.kind is HouseKind.BROILER), key=lambda h: h.number)
    plans: list[HouseSaleOut] = []
    unavailable: list[HouseUnavailableOut] = []
    unmodelled = False
    for house in broilers:
        try:
            plans.append(_house_plan(farm, house, as_of, mode, price, terms))
        except DomainError as err:
            if isinstance(err, NoReferenceCurve) and is_unmodelled_breed(house.breed):
                logger.info("sale for %s: no growth standard (%s)", house.house_id, err.customer_message)
                unmodelled = True
                continue
            unavailable.append(
                HouseUnavailableOut(
                    house_id=house.house_id,
                    number=house.number,
                    label_en=house.label_en,
                    label_te=house.label_te,
                    message_en=err.customer_message,
                    message_te=err.customer_message_te,
                    values=err.values,
                )
            )
    plans.sort(key=lambda p: (p.break_even_day_index is None, p.break_even_day_index or 0))
    parts = [Text("Sell-day check for your broiler sheds.", "మీ బ్రాయిలర్ షెడ్ల అమ్మకం రోజు తనిఖీ.")]
    items = [Text(p.text_en, p.text_te) for p in plans]
    items += [unavailable_text(u) for u in unavailable]
    if unmodelled:  # said once for the farm, after the sheds that could be planned
        items.append(_unmodelled_text(source, price))
    if not plans and not unavailable and not unmodelled:
        parts.append(Text("No broiler sheds to check.", "తనిఖీ చేయడానికి బ్రాయిలర్ షెడ్లు లేవు."))
    parts += items[:MAX_SPOKEN_HOUSES]
    return PlanSaleOutput(
        text_en=" ".join(p.en for p in parts),
        text_te=" ".join(p.te for p in parts),
        demo_data=source.demo_data if unmodelled and not plans else True,
        as_of=as_of.isoformat(),
        farm_mode=mode.value,
        plans=plans,
        unavailable=unavailable,
    )


def register(apps: Apps, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    card = sale_plan_html().replace('"@SERVER_DEMO@"', "true" if source.demo_data else "false")
    apps.add_html_resource(
        SALE_PLAN_URI,
        card,
        name="sale-plan-card",
        title="Sell-day plan card",
        description="Bilingual (Telugu + English) card for plan_sale: profit by day, best day highlighted.",
        prefers_border=False,
    )

    @apps.tool(
        resource_uri=SALE_PLAN_URI,
        name="plan_sale",
        title="Sell-day plan",
        description=DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def plan_sale_tool(
        house: Annotated[str | None, HOUSE_PARAM] = None,
        live_price_per_kg: Annotated[float | None, PRICE_PARAM] = None,
    ) -> Annotated[CallToolResult, PlanSaleOutput]:
        try:
            out = build_plan(source, house, live_price_per_kg)
        except DomainError as err:
            return domain_error_result(err)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name="plan_sale",
            title=Text("When to sell", "ఎప్పుడు అమ్మాలో"),
            example_en="When should I sell shed one?",
        )
    )
