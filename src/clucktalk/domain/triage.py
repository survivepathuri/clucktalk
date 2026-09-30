"""Health triage rules, pure (docs/DESIGN.md §7 rule 3, §18).

The model chooses only from the closed lists below; code owns the safety floor, every number and every word.
- ``Sign``: what the farmer reports, as a closed list (the host maps the farmer's words onto it).
- ``floor_urgency``: a deterministic minimum urgency from the signs and the record book. The model can raise
  urgency but never lower it (``combine``). The floor is CluckTalk's own heuristic built on the warning signs
  published by the sources in ``SOURCES``; it is triage, never a diagnosis.
- ``validate_decision``: the model's reply must be exactly the closed-list schema, or it is rejected.
There is deliberately no medicine, drug or dose anywhere in this module (docs/DESIGN.md §7 rule 3).
Telugu: review status per string in docs/TELUGU_REVIEW.md.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum
from typing import Any

from clucktalk.i18n import Text


class Sign(StrEnum):
    COUGHING = "coughing"
    SNEEZING = "sneezing"
    GASPING = "gasping"
    NASAL_DISCHARGE = "nasal_discharge"
    SWOLLEN_HEAD = "swollen_head"
    DISCOLOURED_COMB = "discoloured_comb"
    TWISTED_NECK = "twisted_neck"
    PARALYSIS = "paralysis"
    DIARRHOEA = "diarrhoea"
    NOT_EATING = "not_eating"
    DULL = "dull"
    LAME = "lame"
    PANTING = "panting"
    SUDDEN_DEATHS = "sudden_deaths"


SIGN_TEXT: dict[Sign, Text] = {
    Sign.COUGHING: Text("coughing", "దగ్గు"),
    Sign.SNEEZING: Text("sneezing", "తుమ్ములు"),
    Sign.GASPING: Text("gasping for air", "ఊపిరి కోసం ఆయాసం"),
    Sign.NASAL_DISCHARGE: Text("runny nose", "ముక్కు కారడం"),
    Sign.SWOLLEN_HEAD: Text("swelling of the head, eyes or neck", "తల, కళ్ళు లేదా మెడ వాపు"),
    Sign.DISCOLOURED_COMB: Text("blue or purple comb, wattles or legs", "తురాయి, గంగడోలు లేదా కాళ్ళు నీలం/ఊదా రంగు"),
    Sign.TWISTED_NECK: Text("twisted neck", "మెడ వంకర తిరగడం"),
    Sign.PARALYSIS: Text("paralysed legs or drooping wings", "కాళ్ళు చచ్చుబడటం లేదా రెక్కలు వాలిపోవడం"),
    Sign.DIARRHOEA: Text("diarrhoea", "విరేచనాలు"),
    Sign.NOT_EATING: Text("not eating", "మేత తినకపోవడం"),
    Sign.DULL: Text("dull or huddled birds", "నీరసంగా ముడుచుకుని ఉండటం"),
    Sign.LAME: Text("lameness", "కుంటడం"),
    Sign.PANTING: Text("panting", "నోరు తెరిచి ఆయాసపడటం"),
    Sign.SUDDEN_DEATHS: Text("sudden deaths", "అకస్మాత్తుగా చనిపోవడం"),
}

# Warning signs that, with sudden deaths, the sources below list for reportable bird diseases (avian influenza,
# Newcastle disease): head swelling, comb/wattle/leg discolouration, twisted neck, paralysis / drooping wings.
RED_FLAG_SIGNS = frozenset({Sign.SWOLLEN_HEAD, Sign.DISCOLOURED_COMB, Sign.TWISTED_NECK, Sign.PARALYSIS})


class Urgency(IntEnum):
    ROUTINE = 0
    WATCH = 1
    URGENT = 2
    NOTIFIABLE_SUSPECT = 3

    @property
    def code(self) -> str:
        return self.name.lower()


class Category(StrEnum):
    RESPIRATORY = "respiratory"
    DIGESTIVE = "digestive"
    LEG_OR_MOVEMENT = "leg_or_movement"
    HEAT_STRESS = "heat_stress"
    WATER_OR_FEED = "water_or_feed_problem"
    NERVOUS = "nervous_signs"


CATEGORY_TEXT: dict[Category, Text] = {
    Category.RESPIRATORY: Text("a breathing problem", "శ్వాస సమస్య"),
    Category.DIGESTIVE: Text("a gut problem", "జీర్ణ సమస్య"),
    Category.LEG_OR_MOVEMENT: Text("a leg or movement problem", "కాళ్ళు లేదా కదలిక సమస్య"),
    Category.HEAT_STRESS: Text("heat stress", "వేడి ఒత్తిడి"),
    Category.WATER_OR_FEED: Text("a water or feed problem", "నీరు లేదా మేత సమస్య"),
    Category.NERVOUS: Text("a nervous-system problem", "నరాల సమస్య"),
}


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


CONFIDENCE_TEXT: dict[Confidence, Text] = {
    Confidence.LOW: Text("low confidence", "తక్కువ నమ్మకం"),
    Confidence.MEDIUM: Text("medium confidence", "మధ్యస్థ నమ్మకం"),
    Confidence.HIGH: Text("high confidence", "ఎక్కువ నమ్మకం"),
}


class Check(StrEnum):
    """Husbandry checks the model may pick. Never a treatment."""

    ISOLATE = "isolate_sick_birds"
    WATER = "check_water"
    VENTILATION = "check_ventilation"
    LITTER = "check_litter"
    TEMPERATURE = "check_temperature"
    FEED = "check_feed"
    REMOVE_DEAD = "remove_dead_birds"
    CALL_VET = "call_vet_today"


class ProtocolStep(StrEnum):
    """The fixed steps for a suspected reportable disease; never chosen by the model."""

    STOP_MOVEMENT = "stop_movement"
    ISOLATE = "isolate_sick_birds"
    DO_NOT_OPEN = "do_not_open_dead_birds"
    REPORT_NOW = "report_now"


CHECK_TEXT: dict[str, Text] = {
    Check.ISOLATE: Text("separate the sick birds", "జబ్బు పడిన కోళ్లను వేరు చేయండి"),
    Check.WATER: Text("check the drinkers and water supply", "తాగే నీరు, డ్రింకర్లు సరిచూడండి"),
    Check.VENTILATION: Text("check ventilation and any ammonia smell", "గాలి ప్రసరణ, అమ్మోనియా వాసన సరిచూడండి"),
    Check.LITTER: Text("check that the litter is dry", "లిట్టర్ పొడిగా ఉందో సరిచూడండి"),
    Check.TEMPERATURE: Text("check the shed temperature", "షెడ్ ఉష్ణోగ్రత సరిచూడండి"),
    Check.FEED: Text("check the feed for mould or a recent change", "మేతలో బూజు లేదా ఇటీవలి మార్పు ఉందో సరిచూడండి"),
    Check.REMOVE_DEAD: Text("remove dead birds quickly and bury them properly", "చనిపోయిన కోళ్లను వెంటనే తీసి సరిగా పూడ్చండి"),
    Check.CALL_VET: Text("call your vet today", "ఈరోజే మీ డాక్టర్‌కి ఫోన్ చేయండి"),
    ProtocolStep.STOP_MOVEMENT: Text(
        "stop all movement of birds, eggs, litter, vehicles and visitors in or out of the shed",
        "షెడ్ లోపలికి, బయటికి కోళ్లు, గుడ్లు, లిట్టర్, వాహనాలు, సందర్శకుల రాకపోకలు ఆపండి",
    ),
    ProtocolStep.DO_NOT_OPEN: Text("do not cut open dead birds", "చనిపోయిన కోళ్లను కోసి తెరవకండి"),
    ProtocolStep.REPORT_NOW: Text(
        "report it today to your vet or the nearest government veterinary centre",
        "ఈరోజే మీ డాక్టర్‌కి లేదా దగ్గరలోని ప్రభుత్వ పశు వైద్యశాలకు తెలియజేయండి",
    ),
}

NOTIFIABLE_PROTOCOL: tuple[str, ...] = (
    ProtocolStep.STOP_MOVEMENT,
    ProtocolStep.ISOLATE,
    ProtocolStep.DO_NOT_OPEN,
    ProtocolStep.REPORT_NOW,
)

MAX_CATEGORIES = 3
MAX_CHECKS = 5

# Every source was read before it was cited (docs/SOURCES.md, "Health triage").
SOURCES: tuple[tuple[str, str], ...] = (
    (
        "Govt. of India, DAHD: Action Plan for Prevention, Control & Containment of Avian Influenza (Revised 2021), "
        "biosecurity section: warning signs; report every unusual sickness or death",
        "https://megahvt.gov.in/notification/revised_AI_Action_Plan_2021.pdf",
    ),
    ("WOAH: Newcastle disease (respiratory and nervous signs)", "https://www.woah.org/en/disease/newcastle-disease/"),
    (
        "USDA APHIS: How to spot sickness in birds",
        "https://www.aphis.usda.gov/livestock-poultry-disease/avian/defend-the-flock/signs-illness",
    ),
)


@dataclass(frozen=True)
class Floor:
    urgency: Urgency
    reasons: tuple[str, ...]  # stable codes, for structuredContent and tests; never spoken


def floor_urgency(signs: frozenset[Sign], mortality_spike: bool, unmapped_words: bool = False) -> Floor:
    """The minimum urgency, from code only. ``mortality_spike`` is the record book's own finding
    (clucktalk.domain.status); the farmer saying "sudden deaths" counts the same. ``unmapped_words``: the farmer
    described something but no sign could be mapped; code can't read the words, so it never calls them less than
    a vet today (Rule 11 review 2026-09-30)."""
    deaths = mortality_spike or Sign.SUDDEN_DEATHS in signs
    red = signs & RED_FLAG_SIGNS
    unread = unmapped_words and not signs
    reasons: list[str] = []
    if red:
        reasons.append("red_flag_sign")
    if mortality_spike:
        reasons.append("mortality_spike")
    if Sign.SUDDEN_DEATHS in signs:
        reasons.append("sudden_deaths_reported")
    if unread:
        reasons.append("words_not_mapped")
    if red and deaths:
        return Floor(Urgency.NOTIFIABLE_SUSPECT, tuple(reasons))
    if red or deaths or unread:
        # DAHD: "Every unusual sickness or death of birds should be immediately reported to the nearest
        # veterinary center": a vet today, even without other signs.
        return Floor(Urgency.URGENT, tuple(reasons))
    if signs:
        return Floor(Urgency.WATCH, ("signs_reported",))
    return Floor(Urgency.ROUTINE, ())


@dataclass(frozen=True)
class Decision:
    """What the model (or the demo rules) decided, closed lists only."""

    urgency: Urgency
    consistent_with: tuple[tuple[Category, Confidence], ...]
    checks: tuple[Check, ...]


class InvalidDecision(ValueError):
    """The model's reply is not exactly the closed-list schema. Logged and retried once, never spoken."""


DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "urgency": {"type": "string", "enum": [u.code for u in Urgency]},
        "consistent_with": {
            "type": "array",
            "maxItems": MAX_CATEGORIES,
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": [c.value for c in Category]},
                    "confidence": {"type": "string", "enum": [c.value for c in Confidence]},
                },
                "required": ["category", "confidence"],
                "additionalProperties": False,
            },
        },
        "checks": {
            "type": "array",
            "maxItems": MAX_CHECKS,
            "items": {"type": "string", "enum": [c.value for c in Check]},
        },
    },
    "required": ["urgency", "consistent_with", "checks"],
    "additionalProperties": False,
}


def validate_decision(raw: Any) -> Decision:
    """Strict: unknown keys, unknown values, wrong types or too many items reject the whole reply."""
    if not isinstance(raw, dict) or set(raw) != {"urgency", "consistent_with", "checks"}:
        raise InvalidDecision(f"keys {sorted(raw) if isinstance(raw, dict) else type(raw).__name__}")
    by_code = {u.code: u for u in Urgency}
    if not isinstance(raw["urgency"], str) or raw["urgency"] not in by_code:
        raise InvalidDecision("urgency")
    cw, checks = raw["consistent_with"], raw["checks"]
    if not isinstance(cw, list) or len(cw) > MAX_CATEGORIES or not isinstance(checks, list) or len(checks) > MAX_CHECKS:
        raise InvalidDecision("list shape")
    pairs: list[tuple[Category, Confidence]] = []
    for item in cw:
        if not isinstance(item, dict) or set(item) != {"category", "confidence"}:
            raise InvalidDecision("consistent_with item")
        try:
            pair = (Category(item["category"]), Confidence(item["confidence"]))
        except ValueError as exc:
            raise InvalidDecision("consistent_with value") from exc
        if pair[0] not in (p[0] for p in pairs):
            pairs.append(pair)
    try:
        picked = tuple(dict.fromkeys(Check(c) for c in checks))
    except ValueError as exc:
        raise InvalidDecision("checks value") from exc
    return Decision(by_code[raw["urgency"]], tuple(pairs), picked)


def combine(floor: Floor, decision: Decision | None) -> Decision:
    """The final decision: never below the floor. A suspected reportable disease names no category (no
    diagnosis) and gets the fixed protocol, whatever the model said."""
    urgency = max(floor.urgency, decision.urgency if decision else Urgency.ROUTINE)
    if urgency is Urgency.NOTIFIABLE_SUSPECT:
        return Decision(urgency, (), ())
    if decision is None:
        return Decision(urgency, (), (Check.CALL_VET,) if urgency >= Urgency.URGENT else ())
    checks = decision.checks
    if urgency >= Urgency.URGENT and Check.CALL_VET not in checks:
        checks = (Check.CALL_VET, *checks)[:MAX_CHECKS]
    return Decision(urgency, decision.consistent_with, checks)


# Demo rules (mock mode, MOCK_BEDROCK=true): a deterministic stand-in for the model, labelled "AI: off".
_RULE_CATEGORIES: tuple[tuple[frozenset[Sign], Category], ...] = (
    (frozenset({Sign.COUGHING, Sign.SNEEZING, Sign.GASPING, Sign.NASAL_DISCHARGE}), Category.RESPIRATORY),
    (frozenset({Sign.DIARRHOEA}), Category.DIGESTIVE),
    (frozenset({Sign.LAME}), Category.LEG_OR_MOVEMENT),
    (frozenset({Sign.PANTING}), Category.HEAT_STRESS),
    (frozenset({Sign.NOT_EATING}), Category.WATER_OR_FEED),
    (frozenset({Sign.TWISTED_NECK, Sign.PARALYSIS}), Category.NERVOUS),
)
_RULE_CHECKS: dict[Category, tuple[Check, ...]] = {
    Category.RESPIRATORY: (Check.ISOLATE, Check.VENTILATION, Check.LITTER),
    Category.DIGESTIVE: (Check.WATER, Check.LITTER, Check.FEED),
    Category.LEG_OR_MOVEMENT: (Check.LITTER,),
    Category.HEAT_STRESS: (Check.TEMPERATURE, Check.WATER, Check.VENTILATION),
    Category.WATER_OR_FEED: (Check.WATER, Check.FEED),
    Category.NERVOUS: (Check.ISOLATE, Check.CALL_VET),
}


def rules_decision(signs: frozenset[Sign], mortality_spike: bool) -> dict[str, Any]:
    """The demo rules' reply, in exactly the model's reply schema (so it goes through the same validator)."""
    cats: list[Category] = [cat for group, cat in _RULE_CATEGORIES if signs & group][:MAX_CATEGORIES]
    checks: list[Check] = []
    for cat in cats:
        checks += [c for c in _RULE_CHECKS[cat] if c not in checks]
    if mortality_spike or Sign.SUDDEN_DEATHS in signs:
        checks = [Check.REMOVE_DEAD, *[c for c in checks if c is not Check.REMOVE_DEAD]]
    urgency = floor_urgency(signs, mortality_spike).urgency
    confidence = Confidence.MEDIUM if len(signs) >= 2 else Confidence.LOW
    return {
        "urgency": urgency.code,
        "consistent_with": [{"category": c.value, "confidence": confidence.value} for c in cats],
        "checks": [c.value for c in checks[:MAX_CHECKS]],
    }


# -- stored checks and handoffs ---------------------------------------------------------------------------------
class CheckStatus(StrEnum):
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


CHECK_ID_PATTERN = r"^chk_[0-9a-f]{16}$"
# Longer than a check can take (2 calls x 15 s timeout + throttle); a check still "analyzing" after this lost its
# job (a crash, a restart, a long queue) and is failed for good: the tool says so, and the job then neither calls
# the model nor turns it "ready" (Rule 11 reviews 2026-09-29 and 2026-09-30).
ANALYZING_TIMEOUT = timedelta(minutes=2)
HANDOFF_ID_PATTERN = r"^vh_[0-9a-f]{16}$"


def new_check_id() -> str:
    return "chk_" + secrets.token_hex(8)


def new_handoff_id() -> str:
    return "vh_" + secrets.token_hex(8)


@dataclass(frozen=True)
class TriageInput:
    """Everything the triage decision may use, captured when the check starts, so the result and the vet
    summary describe the same moment. Numbers come from the record book (code), never from the model."""

    house_id: str
    label_en: str
    label_te: str
    breed: str
    age_days: int | None
    live_birds: int | None
    signs: tuple[Sign, ...]
    symptoms: str | None  # the farmer's own words: prompt data only, never spoken back (docs/DESIGN.md §18)
    birds_affected: int | None
    since_days: int | None
    deaths_latest: int | None
    baseline_daily_avg: float | None  # set only with a mortality spike (the spike finding's own baseline)
    mortality_spike: bool
    feed_drop_pct: float | None
    latest_record_day: str | None
    records_used: bool = True  # False: the shed's records couldn't be used; the check runs on the signs alone
    photo_ref: str | None = None  # a placeholder photo attached (clucktalk.domain.photos); recorded, never analyzed
    birds_affected_ignored: int | None = None  # said count above the live birds: never given to the model, said so


@dataclass(frozen=True)
class TriageResult:
    urgency: Urgency
    consistent_with: tuple[tuple[Category, Confidence], ...]
    checks: tuple[str, ...]  # Check or ProtocolStep values
    engine: str  # "rules" (demo / cap reached), "nova", or a test double's name; "none" = floor only
    model_id: str | None
    ai_note: str | None  # None | "daily_limit" | "not_needed_red_flags"


@dataclass(frozen=True)
class HealthCheck:
    check_id: str
    farm_id: str
    house_id: str
    created_at: datetime
    status: CheckStatus
    input: TriageInput
    floor: Floor
    result: TriageResult | None
    updated_at: datetime

    def timed_out(self, now: datetime) -> bool:
        """Still "analyzing" past ``ANALYZING_TIMEOUT``: the farmer is told it failed, so it stays failed."""
        return self.status is CheckStatus.ANALYZING and now - self.created_at > ANALYZING_TIMEOUT


@dataclass(frozen=True)
class VetHandoff:
    """A case summary sent to the farmer's vet. Always a simulated SMS in this build (docs/DESIGN.md §7 rule 2)."""

    handoff_id: str
    farm_id: str
    check_id: str
    created_at: datetime
    message_en: str
    message_te: str


def input_to_dict(i: TriageInput) -> dict[str, Any]:
    d = asdict(i)
    d["signs"] = [s.value for s in i.signs]
    return d


def input_from_dict(d: dict[str, Any]) -> TriageInput:
    return TriageInput(**{**d, "signs": tuple(Sign(s) for s in d["signs"])})


def result_to_dict(r: TriageResult) -> dict[str, Any]:
    return {
        "urgency": r.urgency.code,
        "consistent_with": [[c.value, conf.value] for c, conf in r.consistent_with],
        "checks": list(r.checks),
        "engine": r.engine,
        "model_id": r.model_id,
        "ai_note": r.ai_note,
    }


def result_from_dict(d: dict[str, Any]) -> TriageResult:
    by_code = {u.code: u for u in Urgency}
    return TriageResult(
        urgency=by_code[d["urgency"]],
        consistent_with=tuple((Category(c), Confidence(conf)) for c, conf in d["consistent_with"]),
        checks=tuple(d["checks"]),
        engine=d["engine"],
        model_id=d["model_id"],
        ai_note=d["ai_note"],
    )


def floor_to_dict(f: Floor) -> dict[str, Any]:
    return {"urgency": f.urgency.code, "reasons": list(f.reasons)}


def floor_from_dict(d: dict[str, Any]) -> Floor:
    return Floor({u.code: u for u in Urgency}[d["urgency"]], tuple(d["reasons"]))
