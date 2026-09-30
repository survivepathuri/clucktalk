"""Health triage + vet handoff: ``start_health_check``, ``get_health_check``, ``prepare_vet_handoff``
(docs/DESIGN.md §3, §5.1, §7 rule 3, §18).

- ``start_health_check`` stores the check and queues the Health Triage agent (clucktalk.agents.triage); it never
  waits for a model (Rule 4). Red-flag signs with deaths are answered at once from code, with no model call.
- ``get_health_check`` reads the stored result: "still checking", the triage, or an honest "couldn't finish".
- ``prepare_vet_handoff`` reads a case summary back and sends it only after "yes" (§5.1); always a Simulated SMS.
Every sentence is a template; every number comes from the record book. The farmer's own words are prompt data
only and are never spoken back. No medicine, drug or dose, ever.
Telugu: review status per string in docs/TELUGU_REVIEW.md.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from clucktalk.agents import AiServices
from clucktalk.agents.triage import floor_only_result, run_triage
from clucktalk.domain.errors import DomainError, NoHealthCheck, NothingToCheck
from clucktalk.domain.houses import resolve_house
from clucktalk.domain.models import House
from clucktalk.domain.photos import LABEL as PHOTO_LABEL
from clucktalk.domain.photos import NOT_ANALYZED, PHOTO_REFS
from clucktalk.domain.proposals import PROPOSAL_TTL, Answer, Proposal, ProposalId, Reason
from clucktalk.domain.status import house_status
from clucktalk.domain.triage import (
    CATEGORY_TEXT,
    CHECK_ID_PATTERN,
    CHECK_TEXT,
    CONFIDENCE_TEXT,
    SIGN_TEXT,
    SOURCES,
    CheckStatus,
    HealthCheck,
    Sign,
    TriageInput,
    Urgency,
    VetHandoff,
    floor_urgency,
    new_check_id,
    new_handoff_id,
)
from clucktalk.i18n import Text
from clucktalk.server.cards import HEALTH_CHECK_URI, health_check_html
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.errors import domain_error_result
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.server.render import num
from clucktalk.server.tools import Capability, CapabilityRegistry

START_TOOL, GET_TOOL, HANDOFF_TOOL = "start_health_check", "get_health_check", "prepare_vet_handoff"
DUPLICATE_WINDOW = timedelta(minutes=10)
# Longer than a check can take (2 calls x 15 s timeout + throttle); a check still "analyzing" after this lost its
# job (a crash or a restart) and is reported as failed, never "still checking" forever (Rule 11 review 2026-09-29).
ANALYZING_TIMEOUT = timedelta(minutes=2)
SPOKEN_CATEGORIES = 2
SPOKEN_CHECKS = 3
SignName = Literal[
    "coughing",
    "sneezing",
    "gasping",
    "nasal_discharge",
    "swollen_head",
    "discoloured_comb",
    "twisted_neck",
    "paralysis",
    "diarrhoea",
    "not_eating",
    "dull",
    "lame",
    "panting",
    "sudden_deaths",
]
PhotoRef = Literal["placeholder_1", "placeholder_2", "placeholder_3"]
assert set(PhotoRef.__args__) == set(PHOTO_REFS)  # the schema enum and the placeholder registry stay one list
assert set(SignName.__args__) == {s.value for s in Sign}  # the schema enum and the domain stay one list
CheckId = Annotated[str, StringConstraints(pattern=CHECK_ID_PATTERN)]

DISCLAIMER = Text(
    "This is guidance, not a diagnosis. Your vet decides any treatment.",
    "ఇది సలహా మాత్రమే, రోగ నిర్ధారణ కాదు. ఏ చికిత్స అయినా మీ డాక్టరే నిర్ణయిస్తారు.",
)
OFFER = Text("Shall I send a summary to your vet?", "మీ డాక్టర్‌కి సారాంశం పంపమంటారా?")
URGENCY_SENTENCE: dict[Urgency, Text] = {
    Urgency.ROUTINE: Text(
        "{h}: this doesn't look urgent right now; keep an eye on the birds.",
        "{h}: ప్రస్తుతం ఇది అత్యవసరంగా కనిపించడం లేదు; కోళ్లను గమనిస్తూ ఉండండి.",
    ),
    Urgency.WATCH: Text("{h}: keep a close watch on the birds today.", "{h}: ఈరోజు కోళ్లను దగ్గరగా గమనించండి."),
    Urgency.URGENT: Text("{h} needs your vet today.", "{h} కి ఈరోజే మీ డాక్టర్ అవసరం."),
    Urgency.NOTIFIABLE_SUSPECT: Text(
        "{h}: these signs together can mean a serious bird disease that must be reported.",
        "{h}: ఈ లక్షణాలు కలిసి ఉంటే, తప్పనిసరిగా తెలియజేయాల్సిన తీవ్రమైన కోళ్ల వ్యాధి కావచ్చు.",
    ),
}
URGENCY_SHORT: dict[Urgency, Text] = {
    Urgency.ROUTINE: Text("not urgent", "అత్యవసరం కాదు"),
    Urgency.WATCH: Text("watch closely today", "ఈరోజు దగ్గరగా గమనించాలి"),
    Urgency.URGENT: Text("needs a vet today", "ఈరోజే డాక్టర్ అవసరం"),
    Urgency.NOTIFIABLE_SUSPECT: Text("signs of a possible reportable disease", "తెలియజేయాల్సిన వ్యాధి లక్షణాలు కావచ్చు"),
}
AI_LABEL: dict[str, Text] = {
    "rules": Text("Demo rules (no AI model)", "డెమో నియమాలు (AI మోడల్ లేదు)"),
    "nova": Text("AI: Amazon Nova on Bedrock", "AI: బెడ్‌రాక్‌పై Amazon Nova"),
    "none": Text("Safety rules only (no AI needed)", "భద్రతా నియమాలు మాత్రమే (AI అవసరం లేదు)"),
}
TEST_MODEL_LABEL = Text("Test model", "పరీక్ష మోడల్")
DAILY_LIMIT_NOTE = Text(
    "Today's AI limit is reached, so this check used the demo rules.",
    "ఈరోజు AI పరిమితి అయిపోయింది, కాబట్టి ఈ తనిఖీకి డెమో నియమాలు వాడాను.",
)
REASON_TEXT: dict[Reason, Text] = {
    "expired": Text("That request timed out, so nothing was sent.", "ఆ అభ్యర్థన సమయం ముగిసింది, కాబట్టి ఏమీ పంపలేదు."),
    "superseded": Text(
        "That request was replaced by a newer one, so nothing was sent.",
        "ఆ అభ్యర్థన స్థానంలో కొత్తది వచ్చింది, కాబట్టి ఏమీ పంపలేదు.",
    ),
    "changed": Text(
        "That's different from what I read back, so nothing was sent yet.",
        "అది నేను చదివి వినిపించిన దానికి భిన్నంగా ఉంది, కాబట్టి ఇంకా ఏమీ పంపలేదు.",
    ),
    "unknown": Text("I couldn't find that request, so nothing was sent.", "ఆ అభ్యర్థన నాకు కనబడలేదు, కాబట్టి ఏమీ పంపలేదు."),
    "cancelled_earlier": Text(
        "That request was already cancelled, so nothing was sent.",
        "ఆ అభ్యర్థన ఇప్పటికే రద్దయింది, కాబట్టి ఏమీ పంపలేదు.",
    ),
    "already_done": Text(
        "That summary was already sent, so saying no now doesn't unsend it.",
        "ఆ సారాంశం ఇప్పటికే పంపబడింది, కాబట్టి ఇప్పుడు 'వద్దు' అన్నా అది వెనక్కి రాదు.",
    ),
}
NOT_SENT = Text("Okay, nothing was sent.", "సరే, ఏమీ పంపలేదు.")


def _join(*parts: Text) -> Text:
    return Text(" ".join(p.en for p in parts if p.en), " ".join(p.te for p in parts if p.te))


AND = Text("and", "మరియు")
OR = Text("or", "లేదా")


def _list(items: list[Text], conj: Text = AND) -> Text:
    if len(items) <= 1:
        return items[0] if items else Text("", "")
    return Text(
        ", ".join(i.en for i in items[:-1]) + f" {conj.en} " + items[-1].en,
        ", ".join(i.te for i in items[:-1]) + f" {conj.te} " + items[-1].te,
    )


# -- output ---------------------------------------------------------------------------------------------------------
class CodeLabelOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    label_en: str
    label_te: str


class CategoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    label_en: str
    label_te: str
    confidence: Literal["low", "medium", "high"]
    confidence_en: str
    confidence_te: str


class EvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latest_record_day: str | None
    deaths_latest: int | None
    records_used: bool
    mortality_spike: bool
    baseline_daily_avg: float | None
    feed_drop_pct: float | None
    live_birds: int | None
    age_days: int | None


class PhotoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    placeholder: Literal[True]  # only placeholder images exist; no real photo has been validated
    analyzed: Literal[False]  # the photo is recorded and shown as attached, never read (docs/DESIGN.md §18)
    label_en: str
    label_te: str
    note_en: str
    note_te: str


class AiOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: str
    model_id: str | None
    label_en: str
    label_te: str
    note: Literal["daily_limit", "not_needed_red_flags"] | None


class SourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    url: str


class HealthCheckOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    check_id: str
    house_id: str
    number: int
    label_en: str
    label_te: str
    status: Literal["analyzing", "ready", "failed"]
    created_at: str
    duplicate: bool  # this start matched a check asked a moment ago; no new check was made
    floor_urgency: Literal["routine", "watch", "urgent", "notifiable_suspect"]
    floor_reasons: list[str]
    urgency: Literal["routine", "watch", "urgent", "notifiable_suspect"] | None
    signs: list[CodeLabelOut]
    consistent_with: list[CategoryOut]
    checks: list[CodeLabelOut]
    evidence: EvidenceOut
    ai: AiOut
    photo: PhotoOut | None
    handoff_offered: bool
    disclaimer_en: str
    disclaimer_te: str
    sources: list[SourceOut]


class VetHandoffOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    demo_data: bool
    status: Literal["needs_confirmation", "changed", "already_set", "cancelled"]
    check_id: str
    house_id: str
    number: int
    label_en: str
    label_te: str
    recipient_en: str
    recipient_te: str
    channel: Literal["simulated_sms"]
    simulated: bool
    message_en: str
    message_te: str
    handoff_id: str | None
    sent_at: str | None
    proposal_id: str | None
    expires_at: str | None
    expires_in_minutes: int | None
    reason: str | None
    replayed: bool


# -- building a check -----------------------------------------------------------------------------------------------
def _input(
    house: House, as_of, signs: tuple[Sign, ...], symptoms, birds_affected, since_days, photo_ref: str | None = None
) -> TriageInput:
    """Facts at the moment the check starts, from the record book (code, never the model)."""
    deaths = latest_day = baseline = drop = live = age = None
    spike = False
    try:
        st = house_status(house, as_of)
    except DomainError:
        st = None  # no usable records: triage runs on the signs alone, and the evidence says so (all None)
    if st is not None:
        deaths, latest_day, live, age = st.deaths_latest, st.latest_record_day.isoformat(), st.live_birds, st.age_days
        for f in st.findings:
            if f.code == "mortality_spike":
                spike, baseline = True, float(f.values["baseline_daily_avg"])
            elif f.code == "feed_intake_drop":
                drop = float(f.values["drop_pct"])
    return TriageInput(
        records_used=st is not None,
        house_id=house.house_id,
        label_en=house.label_en,
        label_te=house.label_te,
        breed=house.breed,
        age_days=age,
        live_birds=live,
        signs=signs,
        symptoms=symptoms,
        birds_affected=birds_affected,
        since_days=since_days,
        deaths_latest=deaths,
        baseline_daily_avg=baseline,
        mortality_spike=spike,
        feed_drop_pct=drop,
        latest_record_day=latest_day,
        photo_ref=photo_ref,
    )


def _effective(check: HealthCheck, now: datetime) -> HealthCheck:
    """A check still "analyzing" past ``ANALYZING_TIMEOUT`` lost its job: it is failed (read-only view)."""
    if check.status is CheckStatus.ANALYZING and now - check.created_at > ANALYZING_TIMEOUT:
        return replace(check, status=CheckStatus.FAILED)
    return check


# -- rendering ------------------------------------------------------------------------------------------------------
def _evidence_text(inp: TriageInput) -> Text:
    parts = []
    if not inp.records_used:
        parts.append(
            Text(
                "I couldn't use this shed's records, so this check is on the signs alone.",
                "ఈ షెడ్ రికార్డులను ఉపయోగించలేకపోయాను, కాబట్టి ఈ తనిఖీ లక్షణాల ఆధారంగా మాత్రమే.",
            )
        )
    if inp.mortality_spike and inp.deaths_latest is not None and inp.baseline_daily_avg is not None:
        d, b = num(inp.deaths_latest), num(inp.baseline_daily_avg)
        parts.append(
            Text(
                f"{d} birds died in the latest count, against about {b} a day before.",
                f"తాజా లెక్కలో {d} కోళ్లు చనిపోయాయి, అంతకుముందు రోజుకు సుమారు {b}.",
            )
        )
    if inp.feed_drop_pct is not None:
        p = num(inp.feed_drop_pct)
        parts.append(Text(f"Feed eaten is {p}% below its recent level.", f"మేత తినడం ఇటీవలి స్థాయి కంటే {p}% తక్కువగా ఉంది."))
    return _join(*parts)


def _urgency_text(u: Urgency, inp: TriageInput) -> Text:
    s = URGENCY_SENTENCE[u]
    return Text(s.en.format(h=inp.label_en), s.te.format(h=inp.label_te))


def _ready_text(check: HealthCheck) -> Text:
    r, inp = check.result, check.input
    assert r is not None
    parts = [_urgency_text(r.urgency, inp), _evidence_text(inp)]
    if r.urgency is Urgency.NOTIFIABLE_SUSPECT:
        steps = _list([CHECK_TEXT[c] for c in r.checks])
        parts.append(Text(f"Now: {steps.en}.", f"ఇప్పుడే: {steps.te}."))
    else:
        if r.consistent_with:
            fits = _list(
                [
                    Text(
                        f"{CATEGORY_TEXT[c].en} ({CONFIDENCE_TEXT[conf].en})",
                        f"{CATEGORY_TEXT[c].te} ({CONFIDENCE_TEXT[conf].te})",
                    )
                    for c, conf in r.consistent_with[:SPOKEN_CATEGORIES]
                ],
                OR,
            )
            parts.append(Text(f"The signs fit {fits.en}.", f"లక్షణాలు {fits.te} కి సరిపోతున్నాయి."))
        if r.checks:
            first = _list([CHECK_TEXT[c] for c in r.checks[:SPOKEN_CHECKS]])
            parts.append(Text(f"First, {first.en}.", f"ముందుగా, {first.te}."))
    if r.ai_note == "daily_limit":
        parts.append(DAILY_LIMIT_NOTE)
    if inp.photo_ref:
        parts.append(NOT_ANALYZED)
    parts.append(DISCLAIMER)
    if r.urgency >= Urgency.URGENT:
        parts.append(OFFER)
    return _join(*parts)


def _analyzing_text(check: HealthCheck, first_time: bool) -> Text:
    inp = check.input
    lead = (
        Text(
            f"I'm checking {inp.label_en} now. Ask me in a few seconds if the health check is ready.",
            f"{inp.label_te} ని ఇప్పుడు తనిఖీ చేస్తున్నాను. కొన్ని సెకన్లలో ఆరోగ్య తనిఖీ సిద్ధమైందా అని అడగండి.",
        )
        if first_time
        else Text(
            f"Still checking {inp.label_en}. Ask me again in a few seconds.",
            f"{inp.label_te} ని ఇంకా తనిఖీ చేస్తున్నాను. కొన్ని సెకన్ల తర్వాత మళ్ళీ అడగండి.",
        )
    )
    if check.floor.urgency >= Urgency.URGENT:
        now = _urgency_text(check.floor.urgency, inp)
        return _join(Text("While I check:", "తనిఖీ చేస్తుండగానే:"), now, _evidence_text(inp), DISCLAIMER, lead)
    return lead


def _failed_text(check: HealthCheck) -> Text:
    inp = check.input
    head = Text(
        f"I couldn't finish the health check for {inp.label_en}.",
        f"{inp.label_te} ఆరోగ్య తనిఖీని పూర్తి చేయలేకపోయాను.",
    )
    if check.floor.urgency >= Urgency.URGENT:
        return _join(head, _urgency_text(check.floor.urgency, inp), _evidence_text(inp), DISCLAIMER, OFFER)
    return _join(
        head,
        Text(
            "Please ask me again in a minute, and call your vet today if birds get worse.",
            "దయచేసి ఒక నిమిషం తర్వాత మళ్ళీ అడగండి; కోళ్ల పరిస్థితి దిగజారితే ఈరోజే డాక్టర్‌కి ఫోన్ చేయండి.",
        ),
        DISCLAIMER,
    )


def _ai_out(check: HealthCheck, ai: AiServices) -> AiOut:
    """Who answered; while a check still runs (or failed), the engine configured to answer it."""
    r = check.result
    engine, model_id, note = (r.engine, r.model_id, r.ai_note) if r else (ai.model.engine, ai.model.model_id, None)
    label = AI_LABEL.get(engine, TEST_MODEL_LABEL)
    return AiOut(engine=engine, model_id=model_id, label_en=label.en, label_te=label.te, note=note)


def _output(
    check: HealthCheck, house: House, source: DemoFarmSource, ai: AiServices, *, first_time: bool, duplicate: bool
) -> HealthCheckOutput:
    inp, r = check.input, check.result
    if check.status is CheckStatus.READY:
        text = _ready_text(check)
    elif check.status is CheckStatus.FAILED:
        text = _failed_text(check)
    else:
        text = _analyzing_text(check, first_time)
    if inp.photo_ref and check.status is not CheckStatus.READY:  # a ready answer already says it (_ready_text)
        text = _join(text, NOT_ANALYZED)
    ready = check.status is CheckStatus.READY and r is not None
    return HealthCheckOutput(
        text_en=text.en,
        text_te=text.te,
        demo_data=source.demo_data,
        check_id=check.check_id,
        house_id=house.house_id,
        number=house.number,
        label_en=house.label_en,
        label_te=house.label_te,
        status=check.status.value,
        created_at=check.created_at.isoformat(),
        duplicate=duplicate,
        floor_urgency=check.floor.urgency.code,
        floor_reasons=list(check.floor.reasons),
        urgency=r.urgency.code if ready else None,
        signs=[CodeLabelOut(code=s.value, label_en=SIGN_TEXT[s].en, label_te=SIGN_TEXT[s].te) for s in inp.signs],
        consistent_with=[
            CategoryOut(
                category=c.value,
                label_en=CATEGORY_TEXT[c].en,
                label_te=CATEGORY_TEXT[c].te,
                confidence=conf.value,
                confidence_en=CONFIDENCE_TEXT[conf].en,
                confidence_te=CONFIDENCE_TEXT[conf].te,
            )
            for c, conf in (r.consistent_with if ready else ())
        ],
        checks=[
            CodeLabelOut(code=c, label_en=CHECK_TEXT[c].en, label_te=CHECK_TEXT[c].te)
            for c in (r.checks if ready else ())
        ],
        evidence=EvidenceOut(
            latest_record_day=inp.latest_record_day,
            deaths_latest=inp.deaths_latest,
            records_used=inp.records_used,
            mortality_spike=inp.mortality_spike,
            baseline_daily_avg=inp.baseline_daily_avg,
            feed_drop_pct=inp.feed_drop_pct,
            live_birds=inp.live_birds,
            age_days=inp.age_days,
        ),
        ai=_ai_out(check, ai),
        photo=None
        if not inp.photo_ref
        else PhotoOut(
            ref=inp.photo_ref,
            placeholder=True,
            analyzed=False,
            label_en=PHOTO_LABEL.en,
            label_te=PHOTO_LABEL.te,
            note_en=NOT_ANALYZED.en,
            note_te=NOT_ANALYZED.te,
        ),
        handoff_offered=(r.urgency if ready else check.floor.urgency) >= Urgency.URGENT,
        disclaimer_en=DISCLAIMER.en,
        disclaimer_te=DISCLAIMER.te,
        sources=[SourceOut(title=t, url=u) for t, u in SOURCES],
    )


def build_start(
    source: DemoFarmSource,
    ai: AiServices,
    house_ref: str,
    signs: list[SignName],
    symptoms: str | None,
    birds_affected: int | None,
    since_days: int | None,
    photo_ref: str | None = None,
) -> HealthCheckOutput:
    farm, as_of = source.snapshot()
    house = resolve_house(farm, house_ref)
    sign_set = tuple(dict.fromkeys(Sign(s) for s in signs))
    words = symptoms.strip() if symptoms and symptoms.strip() else None
    if not sign_set and words is None:
        raise NothingToCheck(house.label_en, house.label_te)
    inp = _input(house, as_of, sign_set, words, birds_affected, since_days, photo_ref)
    now = source.now()
    with source.store.atomic():
        latest = source.store.latest_health_check(farm.farm_id, house.house_id)
        latest = None if latest is None else _effective(latest, now)
        if (
            latest is not None
            and latest.status is not CheckStatus.FAILED
            and now - latest.created_at < DUPLICATE_WINDOW
            and latest.input == inp  # same words AND same record-book facts (new deaths make a new check)
        ):
            return _output(latest, house, source, ai, first_time=False, duplicate=True)
        floor = floor_urgency(frozenset(sign_set), inp.mortality_spike)
        check = HealthCheck(
            new_check_id(), farm.farm_id, house.house_id, now, CheckStatus.ANALYZING, inp, floor, None, now
        )
        if floor.urgency is Urgency.NOTIFIABLE_SUSPECT:
            check = replace(check, status=CheckStatus.READY, result=floor_only_result(floor))
        source.store.add_health_check(check)
    if check.status is CheckStatus.ANALYZING:
        ai.runner.submit(lambda: run_triage(source.store, ai, check.check_id, source.now))
    return _output(check, house, source, ai, first_time=True, duplicate=False)


def _find_check(source: DemoFarmSource, house: House, farm_id: str, check_id: str | None) -> HealthCheck:
    check = (
        source.store.get_health_check(check_id)
        if check_id
        else source.store.latest_health_check(farm_id, house.house_id)
    )
    if check is None or check.farm_id != farm_id or check.house_id != house.house_id:
        raise NoHealthCheck(house.label_en, house.label_te)
    return _effective(check, source.now())


def build_get(source: DemoFarmSource, ai: AiServices, house_ref: str | None, check_id: str | None) -> HealthCheckOutput:
    farm, _ = source.snapshot()
    if house_ref is None:
        if check_id is None:
            raise DomainError(
                "I need to know which shed's health check you mean.",
                "Tell me the shed, for example: is shed 2's health check ready?",
                "ఏ షెడ్ ఆరోగ్య తనిఖీ గురించి అడుగుతున్నారో తెలియాలి.",
                "షెడ్ చెప్పండి, ఉదాహరణకు: షెడ్ 2 ఆరోగ్య తనిఖీ సిద్ధమైందా?",
            )
        found = source.store.get_health_check(check_id)
        if found is None or found.farm_id != farm.farm_id:
            raise NoHealthCheck("that shed", "ఆ షెడ్")
        house_ref = found.house_id
    house = resolve_house(farm, house_ref)
    check = _find_check(source, house, farm.farm_id, check_id)
    return _output(check, house, source, ai, first_time=False, duplicate=False)


# -- vet handoff ----------------------------------------------------------------------------------------------------
RECIPIENT = Text("your vet (demo contact)", "మీ డాక్టర్ (డెమో కాంటాక్ట్)")


def _triage_line(check: HealthCheck) -> Text:
    if check.status is CheckStatus.READY and check.result is not None:
        u = URGENCY_SHORT[check.result.urgency]
        return Text(
            f"CluckTalk triage: {u.en} (guidance, not a diagnosis).",
            f"CluckTalk తనిఖీ: {u.te} (సలహా మాత్రమే, రోగ నిర్ధారణ కాదు).",
        )
    u = URGENCY_SHORT[check.floor.urgency]
    if check.status is CheckStatus.FAILED:
        return Text(
            f"The CluckTalk check could not finish; level from the signs and records: {u.en} (not a diagnosis).",
            f"CluckTalk తనిఖీ పూర్తి కాలేదు; లక్షణాలు, రికార్డుల ప్రకారం స్థాయి: {u.te} (రోగ నిర్ధారణ కాదు).",
        )
    return Text(
        f"The CluckTalk check is still running; level from the signs and records so far: {u.en} (not a diagnosis).",
        f"CluckTalk తనిఖీ ఇంకా జరుగుతోంది; ఇప్పటివరకు లక్షణాలు, రికార్డుల ప్రకారం స్థాయి: {u.te} (రోగ నిర్ధారణ కాదు).",
    )


def _summary(check: HealthCheck) -> Text:
    """The case summary for the vet: record-book numbers and the reported signs, never the farmer's free text."""
    inp = check.input
    parts = [Text(f"{inp.label_en}, {inp.breed}", f"{inp.label_te}, {inp.breed}")]
    if inp.age_days is not None:
        parts.append(Text(f"day {num(inp.age_days)}", f"{num(inp.age_days)}వ రోజు"))
    if inp.live_birds is not None:
        parts.append(Text(f"{num(inp.live_birds)} birds alive", f"{num(inp.live_birds)} కోళ్లు బతికి ఉన్నాయి"))
    head = Text(", ".join(p.en for p in parts) + ".", ", ".join(p.te for p in parts) + ".")
    signs = _list([SIGN_TEXT[s] for s in inp.signs]) if inp.signs else Text("none named", "ఏవీ చెప్పలేదు")
    body = _join(
        head,
        _evidence_text(inp),
        Text(f"Signs reported: {signs.en}.", f"చెప్పిన లక్షణాలు: {signs.te}."),
        _triage_line(check),
        Text("The farmer asks you to call back.", "రైతు మిమ్మల్ని తిరిగి ఫోన్ చేయమని కోరుతున్నారు."),
    )
    return body


def build_handoff(
    source: DemoFarmSource,
    flow: ConfirmFlow,
    house_ref: str,
    check_id: str | None,
    proposal_id: str | None,
    answer: Answer | None,
) -> VetHandoffOutput:
    farm, _ = source.snapshot()
    house = resolve_house(farm, house_ref)
    check = _find_check(source, house, farm.farm_id, check_id)
    summary = _summary(check)
    message = Text(
        f"CluckTalk case summary (Simulated SMS, demo farm). {summary.en}",
        f"CluckTalk కేసు సారాంశం (సిమ్యులేటెడ్ SMS, డెమో ఫారం). {summary.te}",
    )

    def apply(_p: Proposal, now: datetime) -> dict[str, Any]:
        handoff = VetHandoff(new_handoff_id(), farm.farm_id, check.check_id, now, message.en, message.te)
        source.store.add_handoff(handoff)
        return {"handoff_id": handoff.handoff_id}

    result = flow.run(
        farm.farm_id,
        HANDOFF_TOOL,
        {"check_id": check.check_id, "message_en": message.en},  # §5.1 rule 3: "yes" sends only what was read back
        proposal_id,
        answer,
        apply,
        in_place=lambda: source.store.handoff_for_check(check.check_id) is not None,
    )
    sent = source.store.handoff_for_check(check.check_id)
    fields: dict[str, Any] = {
        "demo_data": source.demo_data,
        "check_id": check.check_id,
        "house_id": house.house_id,
        "number": house.number,
        "label_en": house.label_en,
        "label_te": house.label_te,
        "recipient_en": RECIPIENT.en,
        "recipient_te": RECIPIENT.te,
        "channel": "simulated_sms",
        "simulated": True,
        "message_en": message.en,
        "message_te": message.te,
        "handoff_id": None if sent is None else sent.handoff_id,
        "sent_at": None if sent is None else sent.created_at.isoformat(),
        "proposal_id": None,
        "expires_at": None,
        "expires_in_minutes": None,
        "reason": result.reason,
        "replayed": False,
    }
    if result.status == "already_set":
        text = Text(
            f"Your vet already has the summary for this {house.label_en} check (simulated SMS).",
            f"ఈ {house.label_te} తనిఖీ సారాంశం ఇప్పటికే మీ డాక్టర్‌కి పంపబడింది (సిమ్యులేటెడ్ SMS).",
        )
        return VetHandoffOutput(text_en=text.en, text_te=text.te, status="already_set", **fields)
    if result.status == "needs_confirmation":
        p = result.proposal
        assert p is not None
        reason = [REASON_TEXT[result.reason]] if result.reason else []
        ask = Text(
            f"I'll send {RECIPIENT.en} this summary by simulated SMS: {summary.en} "
            "Say yes to send it, or no to keep it.",
            f"{RECIPIENT.te} కి ఈ సారాంశాన్ని సిమ్యులేటెడ్ SMS ద్వారా పంపుతాను: {summary.te} పంపాలంటే 'అవును', వద్దంటే 'వద్దు' అని చెప్పండి.",
        )
        text = _join(*reason, ask)
        fields.update(
            proposal_id=p.proposal_id,
            expires_at=p.expires_at.isoformat(),
            expires_in_minutes=int(PROPOSAL_TTL.total_seconds() // 60),
        )
        return VetHandoffOutput(text_en=text.en, text_te=text.te, status="needs_confirmation", **fields)
    if result.status == "applied":
        fields["replayed"] = result.replayed
        text = Text(
            f"Sent to {RECIPIENT.en} as a simulated SMS.",
            f"{RECIPIENT.te} కి సిమ్యులేటెడ్ SMS గా పంపాను.",
        )
        return VetHandoffOutput(text_en=text.en, text_te=text.te, status="changed", **fields)
    if result.reason == "already_done":
        text = REASON_TEXT["already_done"]
    else:
        text = _join(REASON_TEXT[result.reason], NOT_SENT) if result.reason else NOT_SENT
    return VetHandoffOutput(text_en=text.en, text_te=text.te, status="cancelled", **fields)


# -- registration ---------------------------------------------------------------------------------------------------
START_DESCRIPTION = (
    "Use when the farmer describes signs of illness in a house (shed, kotam): coughing, sneezing, gasping, runny "
    "nose, swelling of the head, blue or purple comb or wattles, twisted neck, paralysis or drooping wings, "
    "diarrhoea, not eating, dull birds, lameness, panting, or sudden deaths. Map what they say onto `signs` and "
    "pass their own words in `symptoms`. Starts a health check that runs in the background: the result says "
    "'analyzing' (ask get_health_check in a few seconds) unless the signs need action at once. Triage only: it "
    "never diagnoses and never suggests a medicine, drug or dose — never put a dose in `symptoms`."
)
GET_DESCRIPTION = (
    "Use when the farmer asks whether a health check is ready or what it found. Give the house, or the check_id "
    "from start_health_check. Read-only."
)
HANDOFF_DESCRIPTION = (
    "Use when the farmer wants their vet to get a summary of a health check. Always two calls: first without "
    "`proposal_id`; nothing is sent and the result reads back the summary. Then call again with the same arguments "
    "plus the returned `proposal_id` and `answer`: 'yes' for an explicit spoken yes (haan, avunu), 'no' for no "
    "(nahi, vaddu). In this demo the message is a simulated SMS."
)
HOUSE_PARAM = Field(description="Which house. Accepts how farmers say it: 'shed 2', 'house two', 'kotam do'.")
SIGNS_PARAM = Field(description="Signs the farmer reports, mapped onto the allowed values. Empty if none fit.")
SYMPTOMS_PARAM = Field(
    default=None, max_length=300, description="The farmer's own words about what they see (optional)."
)
AFFECTED_PARAM = Field(default=None, ge=1, description="About how many birds show the signs, if said.")
SINCE_PARAM = Field(default=None, ge=0, le=60, description="How many days ago it started, if said.")
PHOTO_PARAM = Field(
    default=None,
    description="Optional, demo only: attach one of the placeholder photos. It is recorded and shown as attached, "
    "never analyzed, and it never changes the result. Leave it out unless the farmer attached a photo.",
)
CHECK_PARAM = Field(default=None, description="The check_id from start_health_check.")
PROPOSAL_PARAM = Field(default=None, description="Only on the second call: the proposal_id from the first call.")
ANSWER_PARAM = Field(default=None, description="Only on the second call: 'yes' if the farmer said yes, 'no' if no.")


def _result(out: BaseModel) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=out.text_en)],  # type: ignore[attr-defined]
        structured_content=out.model_dump(mode="json"),
    )


def register_cards(apps: Apps, registry: CapabilityRegistry, source: DemoFarmSource, ai: AiServices) -> None:
    """The two tools that show the triage card (start and get); registered before the server is built."""
    card = health_check_html().replace('"@SERVER_DEMO@"', "true" if source.demo_data else "false")
    apps.add_html_resource(
        HEALTH_CHECK_URI,
        card,
        name="health-check-card",
        title="Health check card",
        description="Bilingual (Telugu + English) card for health checks: urgency, signs, what to check first.",
        prefers_border=False,
    )

    @apps.tool(
        resource_uri=HEALTH_CHECK_URI,
        name=START_TOOL,
        title="Start a health check",
        description=START_DESCRIPTION,
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
    )
    def start_health_check(
        house: Annotated[str, HOUSE_PARAM],
        signs: Annotated[list[SignName], SIGNS_PARAM],
        symptoms: Annotated[str | None, SYMPTOMS_PARAM] = None,
        birds_affected: Annotated[int | None, AFFECTED_PARAM] = None,
        since_days: Annotated[int | None, SINCE_PARAM] = None,
        photo_ref: Annotated[PhotoRef | None, PHOTO_PARAM] = None,
    ) -> Annotated[CallToolResult, HealthCheckOutput]:
        try:
            return _result(build_start(source, ai, house, signs, symptoms, birds_affected, since_days, photo_ref))
        except DomainError as err:
            return domain_error_result(err)

    @apps.tool(
        resource_uri=HEALTH_CHECK_URI,
        name=GET_TOOL,
        title="Health check result",
        description=GET_DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def get_health_check(
        house: Annotated[str | None, Field(default=None, description=HOUSE_PARAM.description)] = None,
        check_id: Annotated[CheckId | None, CHECK_PARAM] = None,
    ) -> Annotated[CallToolResult, HealthCheckOutput]:
        try:
            return _result(build_get(source, ai, house, check_id))
        except DomainError as err:
            return domain_error_result(err)


def register(server: MCPServer, registry: CapabilityRegistry, source: DemoFarmSource) -> None:
    flow = ConfirmFlow(source.store, source.now)

    @server.tool(
        name=HANDOFF_TOOL,
        title="Send a health check to the vet",
        description=HANDOFF_DESCRIPTION,
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
    )
    def prepare_vet_handoff(
        house: Annotated[str, HOUSE_PARAM],
        check_id: Annotated[CheckId | None, CHECK_PARAM] = None,
        proposal_id: Annotated[ProposalId | None, PROPOSAL_PARAM] = None,
        answer: Annotated[Answer | None, ANSWER_PARAM] = None,
    ) -> Annotated[CallToolResult, VetHandoffOutput]:
        try:
            return _result(build_handoff(source, flow, house, check_id, proposal_id, answer))
        except DomainError as err:
            return domain_error_result(err)

    registry.add(
        Capability(
            tool_name=START_TOOL,
            title=Text("Check sick birds", "జబ్బు పడిన కోళ్ల తనిఖీ"),
            example_en="Shed 2 birds are coughing and not eating",
        )
    )
    registry.add(
        Capability(
            tool_name=HANDOFF_TOOL,
            title=Text("Send a health summary to your vet", "మీ డాక్టర్‌కి ఆరోగ్య సారాంశం పంపండి"),
            example_en="Send the shed 2 health check to my vet",
        )
    )
