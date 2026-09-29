"""``log_daily_record``: one-shot voice logging of a house's day (deaths, feed, a weight sample, a medicine or
vaccine given), read back before it's saved (docs/DESIGN.md §5.1, §13.4).

Every field the farmer doesn't mention keeps whatever is already saved for that day, so a later correction
("actually it was 7, not 6") never silently wipes the rest of the day (clucktalk.domain.records.merge_daily_record).
No dose is ever asked for or stored (CLAUDE.md safety rule; clucktalk.domain.models.Treatment has no dose field).
Telugu: review status per string in docs/TELUGU_REVIEW.md.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from clucktalk.domain.errors import DeathsExceedLiveBirds, DomainError, NothingToRecord
from clucktalk.domain.feed import BAG_KG
from clucktalk.domain.houses import resolve_house
from clucktalk.domain.models import DailyRecord, Treatment, TreatmentKind
from clucktalk.domain.proposals import PROPOSAL_TTL, Answer, Proposal, ProposalId, Reason
from clucktalk.domain.records import merge_daily_record, validate_record_day
from clucktalk.i18n import Text
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import num, plural, weekday_en, weekday_te
from clucktalk.server.tools import Capability, CapabilityRegistry

TOOL = "log_daily_record"
TreatmentKindName = Literal["medicine", "vaccine"]
TREATMENT_LABEL = {"medicine": Text("medicine", "మందు"), "vaccine": Text("vaccine", "వ్యాక్సిన్")}

REASON_TEXT: dict[Reason, Text] = {
    "expired": Text("That request timed out, so nothing changed.", "ఆ అభ్యర్థన సమయం ముగిసింది, కాబట్టి ఏమీ మారలేదు."),
    "superseded": Text(
        "That request was replaced by a newer one, so nothing changed.",
        "ఆ అభ్యర్థన స్థానంలో కొత్తది వచ్చింది, కాబట్టి ఏమీ మారలేదు.",
    ),
    "changed": Text(
        "That's different from what I read back, so nothing changed yet.",
        "అది నేను చదివి వినిపించిన దానికి భిన్నంగా ఉంది, కాబట్టి ఇంకా ఏమీ మారలేదు.",
    ),
    "unknown": Text("I couldn't find that request, so nothing changed.", "ఆ అభ్యర్థన నాకు కనబడలేదు, కాబట్టి ఏమీ మారలేదు."),
    "cancelled_earlier": Text(
        "That request was already cancelled, so nothing changed.",
        "ఆ అభ్యర్థన ఇప్పటికే రద్దయింది, కాబట్టి ఏమీ మారలేదు.",
    ),
    "already_done": Text(
        "That record was already saved earlier, so saying no now doesn't undo it.",
        "ఆ రికార్డ్ ఇంతకుముందే సేవ్ అయింది, కాబట్టి ఇప్పుడు 'వద్దు' అన్నా అది వెనక్కి రాదు.",
    ),
}
KEPT = Text("Okay, nothing changed.", "సరే, ఏమీ మారలేదు.")


def _join(*parts: Text) -> Text:
    return Text(" ".join(p.en for p in parts if p.en), " ".join(p.te for p in parts if p.te))


class TreatmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: TreatmentKindName
    name: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=200)


class TreatmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: TreatmentKindName
    name: str
    note: str | None


class DailyRecordOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: str
    deaths: int
    feed_kg: float
    feed_bags: float
    avg_weight_g: float | None
    weight_sample_birds: int | None
    treatments: list[TreatmentOut]


class LogDailyRecordOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    status: Literal["needs_confirmation", "changed", "already_set", "cancelled"]
    house_id: str
    number: int
    label_en: str
    label_te: str
    record: DailyRecordOut | None  # currently saved for that day, after this call
    proposed: DailyRecordOut  # what this call would save, so the read-back is cross-modal
    proposal_id: str | None
    expires_at: str | None
    expires_in_minutes: int | None
    reason: str | None
    replayed: bool


class RecordBookEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    house_id: str
    number: int
    label_en: str
    label_te: str
    logged: bool
    record: DailyRecordOut | None


class RecordBookOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    as_of: str
    houses_logged: int
    houses_total: int
    entries: list[RecordBookEntryOut]


BOOK_TOOL = "get_record_book"
BOOK_DESCRIPTION = (
    "Use when the farmer asks for today's record-book summary: which houses (sheds, kotams) have a record "
    "logged for today and which don't yet. Read-only; today, every house. To log a record, use "
    "log_daily_record instead."
)

DESCRIPTION = (
    "Use when the farmer reports what happened in a house today (or an earlier day): deaths (mar gaye, mare), "
    "feed given in bags of 50 kg (dana, bori), a weight sample (average weight and how many birds were weighed), "
    "or a medicine or vaccine given (dawai, teeka/tika). Give `house` and whichever of `deaths`, `feed_bags`, "
    "`avg_weight_g` + `weight_sample_birds`, or `treatments` the farmer mentioned; omit the rest — an omitted "
    "field keeps whatever is already saved for that day, so a correction ('actually it was 7 dead') only needs "
    "the one changed field, not the whole day again. `day` defaults to today; give an ISO date for an earlier, "
    "unlogged day. Never ask for or record a dose, even if the farmer gives one — name only. Always two calls: "
    "first without `proposal_id`; nothing is saved and the result reads back what will be saved. Then call again "
    "with the same arguments plus the returned `proposal_id` and `answer`: 'yes' for an explicit spoken yes "
    "(haan, avunu), 'no' for no (nahi, vaddu)."
)
HOUSE_PARAM = Field(
    description="Which house. Accepts how farmers say it: 'shed 2', 'house two', 'kotam do', or a house_id."
)
DAY_PARAM = Field(default=None, description="ISO date (YYYY-MM-DD) this record is for. Defaults to today.")
DEATHS_PARAM = Field(default=None, ge=0, description="Birds that died this day. Omit if not mentioned.")
FEED_BAGS_PARAM = Field(default=None, ge=0, description="Bags of standard 50 kg feed given this day.")
WEIGHT_PARAM = Field(default=None, gt=0, description="Average live weight in grams from a sample weighing.")
SAMPLE_PARAM = Field(default=None, gt=0, description="How many birds were weighed to get avg_weight_g.")
TREATMENTS_PARAM = Field(
    default=None, description="Medicines or vaccines given this day, by name only. Never include a dose."
)
PROPOSAL_PARAM = Field(default=None, description="Only on the second call: the proposal_id from the first call.")
ANSWER_PARAM = Field(default=None, description="Only on the second call: 'yes' if the farmer said yes, 'no' if no.")


def _out(rec: DailyRecord) -> DailyRecordOut:
    return DailyRecordOut(
        day=rec.day.isoformat(),
        deaths=rec.deaths,
        feed_kg=rec.feed_kg,
        feed_bags=rec.feed_kg / BAG_KG,
        avg_weight_g=rec.avg_weight_g,
        weight_sample_birds=rec.weight_sample_birds,
        treatments=[TreatmentOut(kind=t.kind.value, name=t.name, note=t.note) for t in rec.treatments],
    )


def _when(day: date, as_of: date) -> Text:
    if day == as_of:
        return Text("today", "ఈరోజు")
    return Text(f"on {weekday_en(day)}", f"{weekday_te(day)} రోజు")


def _given_summary(
    deaths: int | None,
    feed_bags: float | None,
    avg_weight_g: float | None,
    weight_sample_birds: int | None,
    treatments: list[TreatmentIn] | None,
) -> Text:
    parts = []
    if deaths is not None:
        parts.append(
            Text("no deaths", "మరణాలు లేవు") if deaths == 0 else Text(f"{num(deaths)} died", f"{num(deaths)} కోళ్లు చనిపోయాయి")
        )
    if feed_bags is not None:
        b = num(feed_bags)
        parts.append(Text(f"{b} {plural(int(feed_bags), 'bag', 'bags')} of feed", f"{b} బస్తాల ఫీడ్"))
    if avg_weight_g is not None:
        parts.append(
            Text(
                f"average weight {num(avg_weight_g)} grams from {num(weight_sample_birds)} birds weighed",
                f"{num(weight_sample_birds)} కోళ్లను తూచగా సగటు బరువు {num(avg_weight_g)} గ్రాములు",
            )
        )
    for t in treatments or ():
        label = TREATMENT_LABEL[t.kind]
        parts.append(Text(f"{t.name} {label.en} given", f"{t.name} {label.te} ఇచ్చారు"))
    return Text(", ".join(p.en for p in parts), ", ".join(p.te for p in parts))


def _record_summary(rec: DailyRecord) -> Text:
    """Every field of an already-saved record, for the record-book summary (unlike ``_given_summary``'s
    "only what was just said" framing, deaths and feed are always shown since a saved record always has both)."""
    return _given_summary(
        rec.deaths, rec.feed_kg / BAG_KG, rec.avg_weight_g, rec.weight_sample_birds, list(rec.treatments)
    )


def build_record_book(source: DemoFarmSource) -> RecordBookOutput:
    farm, as_of = source.snapshot()
    entries: list[RecordBookEntryOut] = []
    house_parts: list[Text] = []
    for house in sorted(farm.houses, key=lambda h: h.number):
        stored = next((r for r in source.store.records(farm.farm_id, house.house_id) if r.day == as_of), None)
        entries.append(
            RecordBookEntryOut(
                house_id=house.house_id,
                number=house.number,
                label_en=house.label_en,
                label_te=house.label_te,
                logged=stored is not None,
                record=None if stored is None else _out(stored),
            )
        )
        if stored is None:
            house_parts.append(
                Text(f"No entry yet for {house.label_en} today.", f"{house.label_te}కి ఈరోజు ఇంకా నమోదు కాలేదు.")
            )
        else:
            summary = _record_summary(stored)
            house_parts.append(
                Text(f"{house.label_en} logged: {summary.en}.", f"{house.label_te}: {summary.te} నమోదు అయింది.")
            )
    logged = sum(1 for e in entries if e.logged)
    head = Text(
        f"{num(logged)} of {num(len(entries))} houses logged today.",
        f"ఈరోజు {num(len(entries))} షెడ్లలో {num(logged)} నమోదు అయ్యాయి.",
    )
    return RecordBookOutput(
        text_en=" ".join([head.en, *(p.en for p in house_parts)]),
        text_te=" ".join([head.te, *(p.te for p in house_parts)]),
        demo_data=source.demo_data,
        as_of=as_of.isoformat(),
        houses_logged=logged,
        houses_total=len(entries),
        entries=entries,
    )


def build_log_record(
    source: DemoFarmSource,
    flow: ConfirmFlow,
    house_ref: str,
    day: date | None,
    deaths: int | None,
    feed_bags: float | None,
    avg_weight_g: float | None,
    weight_sample_birds: int | None,
    treatments_in: list[TreatmentIn] | None,
    proposal_id: str | None,
    answer: Answer | None,
) -> LogDailyRecordOutput:
    farm, as_of = source.snapshot()
    farm_id = farm.farm_id
    house = resolve_house(farm, house_ref)
    record_day = day if day is not None else as_of
    validate_record_day(house, record_day, as_of)

    def stored_for(d: date) -> DailyRecord | None:
        return next((r for r in source.store.records(farm_id, house.house_id) if r.day == d), None)

    def on_file(d: date) -> DailyRecord | None:
        """What a correction should be layered onto: the farmer's own earlier log for that day if there is
        one, else the seed's synthetic guess (``house.records`` is already overlaid, farm_state.overlay_records)
        — never a blank day, so a partial first log (e.g. only deaths) doesn't zero out the day's real feed_kg."""
        return next((r for r in house.records if r.day == d), None)

    existing = on_file(record_day)
    feed_kg = None if feed_bags is None else feed_bags * BAG_KG
    if deaths is None and feed_kg is None and avg_weight_g is None and not treatments_in:
        raise NothingToRecord(house.label_en, house.label_te)
    if deaths is not None:
        live_before = house.live_birds(record_day - timedelta(days=1))
        if deaths > live_before:
            raise DeathsExceedLiveBirds(house.label_en, house.label_te, deaths, live_before)

    treatments_tuple = (
        None
        if treatments_in is None
        else tuple(Treatment(TreatmentKind(t.kind), t.name, t.note) for t in treatments_in)
    )
    # Raises WeightSampleNeedsBirdCount early (before proposing) if the pairing is wrong.
    merge_daily_record(existing, record_day, deaths, feed_kg, avg_weight_g, weight_sample_birds, treatments_tuple,
                        house.label_en, house.label_te)  # fmt: skip

    args: dict[str, Any] = {
        "house_id": house.house_id,
        "day": record_day.isoformat(),
        "deaths": deaths,
        "feed_kg": feed_kg,
        "avg_weight_g": avg_weight_g,
        "weight_sample_birds": weight_sample_birds,
        "treatments": None
        if treatments_tuple is None
        else [{"kind": t.kind.value, "name": t.name, "note": t.note} for t in treatments_tuple],
    }

    def apply(proposal: Proposal, _now: datetime) -> dict[str, Any]:
        a = proposal.arguments
        d = date.fromisoformat(a["day"])
        pt = (
            None
            if a["treatments"] is None
            else tuple(Treatment(TreatmentKind(t["kind"]), t["name"], t["note"]) for t in a["treatments"])
        )
        rec = merge_daily_record(
            on_file(d), d, a["deaths"], a["feed_kg"], a["avg_weight_g"], a["weight_sample_birds"], pt,
            house.label_en, house.label_te,
        )  # fmt: skip
        source.store.put_record(farm_id, house.house_id, rec)
        return {"day": rec.day.isoformat()}

    def in_place() -> bool:
        merged = merge_daily_record(
            existing, record_day, deaths, feed_kg, avg_weight_g, weight_sample_birds, treatments_tuple,
            house.label_en, house.label_te,
        )  # fmt: skip
        return merged == existing

    result = flow.run(farm_id, TOOL, args, proposal_id, answer, apply, in_place=in_place)
    saved = stored_for(record_day)
    proposed = merge_daily_record(
        existing, record_day, deaths, feed_kg, avg_weight_g, weight_sample_birds, treatments_tuple,
        house.label_en, house.label_te,
    )  # fmt: skip
    when = _when(record_day, as_of)
    given = _given_summary(deaths, feed_bags, avg_weight_g, weight_sample_birds, treatments_in)
    fields: dict[str, Any] = {
        "demo_data": source.demo_data,
        "house_id": house.house_id,
        "number": house.number,
        "label_en": house.label_en,
        "label_te": house.label_te,
        "record": None if saved is None else _out(saved),
        "proposed": _out(proposed),
        "proposal_id": None,
        "expires_at": None,
        "expires_in_minutes": None,
        "reason": result.reason,
        "replayed": False,
    }
    if result.status == "already_set":
        text = Text(
            f"{house.label_en} already has that recorded for {when.en}, so nothing changed.",
            f"{house.label_te}కి {when.te} అది ఇప్పటికే రికార్డ్ అయింది, కాబట్టి ఏమీ మారలేదు.",
        )
        return LogDailyRecordOutput(text_en=text.en, text_te=text.te, status="already_set", **fields)
    if result.status == "needs_confirmation":
        p = result.proposal
        assert p is not None
        reason = [REASON_TEXT[result.reason]] if result.reason else []
        note = (
            Text(
                f"{house.label_en} already has a record for {when.en}; I'll add this to it.",
                f"{house.label_te}కి {when.te} రికార్డ్ ఇప్పటికే ఉంది; దీన్ని దానికి జోడిస్తాను.",
            )
            if existing is not None
            else Text("", "")
        )
        ask = Text(
            f"For {house.label_en}, {when.en}: {given.en}. Say yes to save, or no to keep it as it is.",
            f"{house.label_te}కి, {when.te}: {given.te}. సేవ్ చేయాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
        )
        text = _join(*reason, note, ask)
        fields.update(
            proposal_id=p.proposal_id,
            expires_at=p.expires_at.isoformat(),
            expires_in_minutes=int(PROPOSAL_TTL.total_seconds() // 60),
        )
        return LogDailyRecordOutput(text_en=text.en, text_te=text.te, status="needs_confirmation", **fields)
    if result.status == "applied":
        fields["replayed"] = result.replayed
        text = Text(f"Done. Saved for {house.label_en}, {when.en}.", f"సరే. {house.label_te}కి, {when.te} సేవ్ చేశాను.")
        return LogDailyRecordOutput(text_en=text.en, text_te=text.te, status="changed", **fields)
    if result.reason == "already_done":
        text = REASON_TEXT["already_done"]
    else:
        text = _join(REASON_TEXT[result.reason], KEPT) if result.reason else KEPT
    return LogDailyRecordOutput(text_en=text.en, text_te=text.te, status="cancelled", **fields)


def register(server: MCPServer, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    flow = ConfirmFlow(source.store, source.now)

    @server.tool(
        name=BOOK_TOOL,
        title="Today's record book",
        description=BOOK_DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def get_record_book() -> Annotated[CallToolResult, RecordBookOutput]:
        out = build_record_book(source)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name=BOOK_TOOL,
            title=Text("Today's record book", "ఈరోజు రికార్డ్ బుక్"),
            example_en="Which houses have logged their record today?",
        )
    )

    @server.tool(
        name=TOOL,
        title="Log a daily record",
        description=DESCRIPTION,
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
    )
    def log_daily_record(
        house: Annotated[str, HOUSE_PARAM],
        day: Annotated[date | None, DAY_PARAM] = None,
        deaths: Annotated[int | None, DEATHS_PARAM] = None,
        feed_bags: Annotated[float | None, FEED_BAGS_PARAM] = None,
        avg_weight_g: Annotated[float | None, WEIGHT_PARAM] = None,
        weight_sample_birds: Annotated[int | None, SAMPLE_PARAM] = None,
        treatments: Annotated[list[TreatmentIn] | None, TREATMENTS_PARAM] = None,
        proposal_id: Annotated[ProposalId | None, PROPOSAL_PARAM] = None,
        answer: Annotated[Answer | None, ANSWER_PARAM] = None,
    ) -> Annotated[CallToolResult, LogDailyRecordOutput]:
        try:
            out = build_log_record(
                source, flow, house, day, deaths, feed_bags, avg_weight_g, weight_sample_birds, treatments,
                proposal_id, answer,
            )  # fmt: skip
        except DomainError as err:
            return domain_error_result(err)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)], structured_content=out.model_dump(mode="json")
        )

    registry.add(
        Capability(
            tool_name=TOOL,
            title=Text("Log today's record", "ఈరోజు రికార్డ్ నమోదు చేయండి"),
            example_en="House 2, 3 birds died and 2 bags of feed today",
        )
    )
