"""``get_daily_briefing``: what needs the farmer's attention today, ranked (docs/DESIGN.md §6, §18).

Voice: the top 3 items, then an offer of "more" (the rest, at most 5 items in all: the Alexa+ voice rule). Screen: a
carousel of the same items. Every sentence is a template and every number comes from the record book, the feed maths
or a stored health check; the model (slow path, clucktalk.agents.briefing) may only re-order the non-health items and
its reply has no text. Health items always come first. No medicine, drug or dose, ever. The sale item is a day, not a
rupee figure, and is labelled Simulated. Telugu: review status per string in docs/TELUGU_REVIEW.md.
The tool only reads: it computes the facts in a few milliseconds and never waits for a model (Rule 4).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.apps import Apps
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from clucktalk.agents import AiServices
from clucktalk.agents.briefing import BriefingRanker, RankView
from clucktalk.domain.briefing import (
    MAX_ITEMS,
    SPOKEN_ITEMS,
    Category,
    Fact,
    apply_order,
    collect_facts,
)
from clucktalk.domain.follow_up import FollowUp, FollowUpState
from clucktalk.domain.models import Farm, House
from clucktalk.domain.status import Finding, Level
from clucktalk.domain.triage import HealthCheck, Urgency
from clucktalk.i18n import Text
from clucktalk.server.cards import BRIEFING_URI, briefing_html
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import num
from clucktalk.server.tools import Capability, CapabilityRegistry
from clucktalk.server.tools.farm_status import SAFETY_STEP, _feed_stock_finding, _finding
from clucktalk.server.tools.follow_up import check_said_text, follow_up_text, shed_health
from clucktalk.server.tools.follow_up import when_ago as _when
from clucktalk.server.tools.health import AI_LABEL, DISCLAIMER, TEST_MODEL_LABEL

TOOL = "get_daily_briefing"
LevelName = Literal["alert", "watch", "info"]
_LEVEL_NAME: dict[Level, LevelName] = {Level.ALERT: "alert", Level.WATCH: "watch", Level.OK: "info"}

HEAD = Text("Here's your briefing for today.", "ఈరోజు మీ బ్రీఫింగ్ ఇది.")
HEAD_REST = Text("Here's the rest.", "మిగిలినవి ఇవి.")
NOTHING = Text("Nothing needs your attention today.", "ఈరోజు మీ శ్రద్ధ అవసరమయ్యేది ఏమీ లేదు.")
MORE_OFFER = Text("Say 'more' to hear the rest.", "మిగిలినవి వినాలంటే 'మరిన్ని' అనండి.")
ALL_DONE = Text("That's everything for today.", "ఈరోజుకు ఇంతే.")
SEE_MORE = Text("There are more things; ask about one shed for details.", "ఇంకా విషయాలు ఉన్నాయి; వివరాల కోసం ఒక షెడ్ గురించి అడగండి.")
ASK_RESULT = Text("Ask me for the health check result.", "ఆరోగ్య తనిఖీ ఫలితం కోసం నన్ను అడగండి.")
ASK_SALE = Text("Ask me for the sell-day plan.", "అమ్మకం రోజు ప్రణాళిక కోసం నన్ను అడగండి.")
AND = Text("and", "మరియు")

AI_ORDERED = Text(
    "Health items come first by safety rules; AI (Amazon Nova on Bedrock) orders the other items in the first three.",
    "ఆరోగ్య అంశాలు భద్రతా నియమాల ప్రకారం ముందుంటాయి; మొదటి మూడింటిలో మిగిలిన అంశాల క్రమాన్ని AI (బెడ్‌రాక్‌పై Amazon Nova) నిర్ణయించింది.",
)
AI_UNREADABLE = Text(
    "The saved AI ordering was unreadable, so the items are in the rules order.",
    "సేవ్ చేసిన AI క్రమం చదవడానికి వీలుకాలేదు, కాబట్టి అంశాలు నియమాల క్రమంలో ఉన్నాయి.",
)
AI_PREPARING = Text(
    "AI ordering is still preparing; showing the rules order for now.",
    "AI క్రమం ఇంకా సిద్ధమవుతోంది; ప్రస్తుతం నియమాల క్రమం చూపిస్తున్నాను.",
)
AI_NO_ANSWER = Text(
    "AI ordering didn't finish, so the items are in the rules order.",
    "AI క్రమం పూర్తి కాలేదు, కాబట్టి అంశాలు నియమాల క్రమంలో ఉన్నాయి.",
)
AI_LIMIT = Text(
    "Today's AI limit is reached, so the items are in the rules order.",
    "ఈరోజు AI పరిమితి అయిపోయింది, కాబట్టి అంశాలు నియమాల క్రమంలో ఉన్నాయి.",
)
SIMULATED = Text("simulated estimate", "అంచనా (డెమో)")


class ItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rank: int
    fact_id: str
    category: str
    level: LevelName
    pinned: bool  # a health item: above everything, never re-ordered by the AI
    simulated: bool  # built on simulated data (the sale item), labelled so in its text
    spoken: bool  # read out in this answer
    house_id: str | None
    number: int | None
    label_en: str | None
    label_te: str | None
    text_en: str
    text_te: str
    values: dict[str, Any]


class BriefingAiOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: str  # who ordered the non-health items: "rules", "none" (nothing to order), or the model engine
    model_id: str | None
    label_en: str
    label_te: str
    note: Literal["in_progress", "no_answer", "daily_limit", "not_needed", "unreadable"] | None


class BriefingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    as_of: str
    level: Literal["alert", "watch", "info", "none"]
    items: list[ItemOut]  # at most MAX_ITEMS, in the order to read them
    total_items: int  # every fact found today; items holds the first MAX_ITEMS
    more_available: bool  # this answer read the first few and "more" reads the rest
    ai: BriefingAiOut


DESCRIPTION = (
    "Use when the farmer asks for today's briefing, the daily update, or what needs attention on the farm today. "
    "Returns at most 5 ranked items (health alerts always first) and reads the top 3; set `more` to true when the "
    "farmer says 'more' to hear the rest. Takes no shed: it covers the whole farm. Never gives a medicine or dose."
)
MORE_PARAM = Field(default=False, description="True only when the farmer asks to hear more after the first items.")


def _label(house: House) -> Text:
    return Text(house.label_en, house.label_te)


def _sale_when(index: int) -> Text:
    if index <= 0:
        return Text("today", "ఈరోజు")
    if index == 1:
        return Text("tomorrow", "రేపు")
    return Text(f"in {index} days", f"{index} రోజుల్లో")


def _join(*parts: Text) -> Text:
    return Text(" ".join(p.en for p in parts if p.en), " ".join(p.te for p in parts if p.te))


def _prefixed(label: Text, body: Text) -> Text:
    return Text(f"{label.en}: {body.en}", f"{label.te}: {body.te}")


def _house_list(labels: list[Text]) -> Text:
    if len(labels) <= 1:
        return labels[0]
    return Text(
        ", ".join(x.en for x in labels[:-1]) + f" {AND.en} " + labels[-1].en,
        ", ".join(x.te for x in labels[:-1]) + f" {AND.te} " + labels[-1].te,
    )


def _natural(values: dict[str, Any]) -> dict[str, Any]:
    """Whole-number floats as ints (the status model stores every number as a float): 26, not 26.0."""
    return {k: int(x) if isinstance(x, float) and x.is_integer() else x for k, x in values.items()}


def _render(fact: Fact, farm: Farm) -> tuple[Text, dict[str, Any]]:
    """The item's sentence and the numbers it speaks, from the fact only (cross-modal, docs/DESIGN.md §6)."""
    house = next((h for h in farm.houses if h.house_id == fact.house_id), None)
    v = fact.values
    match fact.category:
        case Category.NOT_LOGGED_TODAY:
            labels = [Text(f"House {n}", f"షెడ్ {n}") for n in v["numbers"]]
            listed = _house_list(labels)
            text = Text(f"No entry yet today for {listed.en}.", f"ఈరోజు ఇంకా నమోదు కాలేదు: {listed.te}.")
            return text, {"count": v["count"], "numbers": list(v["numbers"])}
        case _ if house is None:
            raise ValueError(f"fact {fact.fact_id!r} names no house")
        case Category.NOT_CHECKED:
            en, te = v["message_en"], v["message_te"]
            text = Text(
                en if house.label_en in en else f"For {house.label_en}: {en}",
                te if house.label_te in te else f"{house.label_te}: {te}",
            )
            return text, {}
        case Category.FEED_STOCK_LOW:
            out = _feed_stock_finding(int(v["days_covered"]), float(v["stock_kg"]))
            return _prefixed(_label(house), Text(out.text_en, out.text_te)), {"days_covered": int(v["days_covered"])}
        case Category.FEED_INTAKE_DROP:  # short for the ear: the drop only, no grams (status has the detail)
            drop = round(float(v["drop_pct"]))
            body = Text(f"Birds ate {drop}% less than expected.", f"కోళ్లు అంచనా కంటే {drop}% తక్కువ తిన్నాయి.")
            return _prefixed(_label(house), body), {"drop_pct": drop}
        case Category.RECENT_LOGGED_SPIKE:
            deaths, base, ago = int(v["deaths"]), round(float(v["baseline_daily_avg"])), int(v["days_ago"])
            when = _when(ago)
            if base == 0:
                en = f"{num(deaths)} birds died {when.en}, after hardly any deaths the week before."
                te = f"{when.te} {num(deaths)} కోళ్లు చనిపోయాయి; అంతకు ముందు వారం దాదాపు ఏవీ చనిపోలేదు."
            else:
                en = f"{num(deaths)} birds died {when.en}, against about {num(base)} a day the week before."
                te = f"{when.te} {num(deaths)} కోళ్లు చనిపోయాయి; అంతకు ముందు వారం రోజుకు సుమారు {num(base)}."
            return _prefixed(_label(house), Text(en, te)), {
                "deaths": deaths,
                "baseline_per_day": base,
                "days_ago": ago,
            }
        case Category.OPEN_HEALTH_CHECK:
            ago = int(v["days_ago"])
            urgency = next(u for u in Urgency if u.code == v["urgency"])
            said = check_said_text(_label(house), urgency, ago, v.get("ready", True))
            return _join(said, ASK_RESULT), {"urgency": v["urgency"], "days_ago": ago}
        case Category.FOLLOW_UP:
            ago = int(v["days_ago"])
            urgency = next(u for u in Urgency if u.code == v["urgency"])
            fup_text = follow_up_text(FollowUpState(v["state"]), urgency, _label(house), ago)
            return fup_text, {"urgency": v["urgency"], "state": v["state"], "days_ago": ago}
        case Category.SALE_WINDOW:
            index = int(v["best_day_index"])
            when = _sale_when(index)
            body = Text(
                f"may be near its best time to sell: the best day looks like {when.en} ({SIMULATED.en}).",
                f"అమ్మడానికి మంచి సమయం దగ్గరలో ఉండవచ్చు: మంచి రోజు {when.te} ({SIMULATED.te}).",
            )
            return _join(_prefixed(_label(house), body), ASK_SALE), {
                "best_day_index": index,
                "best_day": v["best_day"],
            }
        case _:  # a status finding: the same wording as get_farm_status, so voice and status never disagree
            out = _finding(Finding(fact.category.value, fact.level, v), house.breed, fact.is_today)
            return _prefixed(_label(house), Text(out.text_en, out.text_te)), _natural(out.values)


def _ai_out(view: RankView) -> BriefingAiOut:
    if view.note == "in_progress":
        label = AI_PREPARING
    elif view.note == "no_answer":
        label = AI_NO_ANSWER
    elif view.note == "daily_limit":
        label = AI_LIMIT
    elif view.note == "unreadable":
        label = AI_UNREADABLE
    elif view.engine in ("rules", "none"):
        label = AI_LABEL[view.engine]
    elif view.engine == "nova":
        label = AI_ORDERED
    else:
        label = TEST_MODEL_LABEL
    return BriefingAiOut(
        engine=view.engine,
        model_id=view.model_id,
        label_en=label.en,
        label_te=label.te,
        note=view.note,  # type: ignore[arg-type]
    )


def _needs_safety_step(item: ItemOut) -> bool:
    """A death alert, or a stored check that says urgent or a suspected reportable disease: the same next step."""
    if item.category in ("mortality_spike", "recent_logged_spike", "cum_mortality_high"):
        return item.pinned
    # an urgent or reportable check keeps its vet line the day after, when the follow-up item carries the check
    return item.category in ("open_health_check", "follow_up") and item.values.get("urgency") in (
        "urgent",
        "notifiable_suspect",
    )


def _closing(page: list[ItemOut]) -> list[Text]:
    closings: list[Text] = []
    if any(_needs_safety_step(i) for i in page):
        closings.append(SAFETY_STEP)
    if any(i.category in ("open_health_check", "follow_up") for i in page):
        closings.append(DISCLAIMER)
    return closings


def build_briefing(source: DemoFarmSource, ranker: BriefingRanker, more: bool = False) -> BriefingOutput:
    farm, as_of = source.snapshot()
    store = source.store
    checks = {}
    recent: dict[str, tuple[HealthCheck, ...]] = {}
    handed_off: set[str] = set()
    logged: set[str] = set()
    follow_ups: dict[str, FollowUp] = {}
    for house in farm.houses:
        health = shed_health(source, farm.farm_id, house, as_of)  # stored checks + answers + the date: no model
        if health.follow_up is not None and health.follow_up.state in (FollowUpState.ESCALATED, FollowUpState.DUE):
            follow_ups[house.house_id] = health.follow_up
        if health.check is not None:
            checks[house.house_id] = health.check
        recent[house.house_id] = health.recent
        handed_off |= health.handed_off
        if any(r.day == as_of for r in store.records(farm.farm_id, house.house_id)):
            logged.add(house.house_id)
    facts = collect_facts(farm, as_of, checks, frozenset(logged), recent, frozenset(handed_off), follow_ups)
    view = ranker.view(farm.farm_id, as_of, facts)
    # The split between the first three (read first) and the rest ("more") always comes from the rules order, so
    # "more" reads what the first answer promised whatever the AI has stored since (Rule 11 review 2026-09-30, M1).
    # The AI order (never on "more") only re-orders the non-health items inside the first three.
    ordered = facts if more else (*apply_order(facts[:SPOKEN_ITEMS], view.order), *facts[SPOKEN_ITEMS:])
    shown = ordered[:MAX_ITEMS]
    spoken_range = range(SPOKEN_ITEMS, len(shown)) if more else range(min(SPOKEN_ITEMS, len(shown)))

    items: list[ItemOut] = []
    for index, fact in enumerate(shown):
        text, values = _render(fact, farm)
        house = next((h for h in farm.houses if h.house_id == fact.house_id), None)
        items.append(
            ItemOut(
                rank=index + 1,
                fact_id=fact.fact_id,
                category=fact.category.value,
                level=_LEVEL_NAME[fact.level],
                pinned=fact.pinned,
                simulated=fact.simulated,
                spoken=index in spoken_range,
                house_id=fact.house_id,
                number=fact.number,
                label_en=None if house is None else house.label_en,
                label_te=None if house is None else house.label_te,
                text_en=text.en,
                text_te=text.te,
                values=values,
            )
        )
    page = [i for i in items if i.spoken]
    more_available = not more and len(items) > SPOKEN_ITEMS
    if not ordered:
        parts = [NOTHING]
    elif more:
        parts = [HEAD_REST if page else ALL_DONE, *(Text(i.text_en, i.text_te) for i in page)]
        if len(ordered) > MAX_ITEMS:
            parts.append(SEE_MORE)
    else:
        parts = [HEAD, *(Text(i.text_en, i.text_te) for i in page)]
        if more_available:
            parts.append(MORE_OFFER)
    parts += _closing(page)
    level: Literal["alert", "watch", "info", "none"] = (
        "none" if not ordered else _LEVEL_NAME[max((f.level for f in ordered), default=Level.OK)]
    )
    return BriefingOutput(
        text_en=" ".join(p.en for p in parts),
        text_te=" ".join(p.te for p in parts),
        demo_data=source.demo_data,
        as_of=as_of.isoformat(),
        level=level,
        items=items,
        total_items=len(ordered),
        more_available=more_available,
        ai=_ai_out(view),
    )


def register_cards(apps: Apps, registry: CapabilityRegistry, source: DemoFarmSource, ai: AiServices) -> None:
    """Card-bearing, so registered before the server is built (like the triage and status tools)."""
    ranker = BriefingRanker(source.store, ai, source.now)
    card = briefing_html().replace('"@SERVER_DEMO@"', "true" if source.demo_data else "false")
    apps.add_html_resource(
        BRIEFING_URI,
        card,
        name="briefing-card",
        title="Daily briefing card",
        description="Bilingual (Telugu + English) carousel card for get_daily_briefing: the ranked items for today.",
        prefers_border=False,
    )

    # Read-only for the farm: the only thing it may write is a cache of the AI ordering (never farm data).
    @apps.tool(
        resource_uri=BRIEFING_URI,
        name=TOOL,
        title="Daily briefing",
        description=DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def get_daily_briefing(more: Annotated[bool, MORE_PARAM] = False) -> Annotated[CallToolResult, BriefingOutput]:
        out = build_briefing(source, ranker, more)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name=TOOL,
            title=Text("Today's briefing", "ఈరోజు బ్రీఫింగ్"),
            example_en="What's today's briefing?",
        )
    )
