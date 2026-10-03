"""The structured `safety` field of the daily briefing and the farm status (review finding M6, stage 1, Step 47C).

Alexa+ composes its own speech from `structuredContent` and the tool descriptions, so the safety step must not live in
prose alone. This is the ONE place that derives the field, only from rules that already exist:

* ``level`` is the card's own level word mapped to OK / WATCH / ALERT / UNKNOWN, so it is equal to the card level and
  can never be lower than the rules that set that level (it is raised to a fact's level when the card is lower);
* ``reason_codes`` are the existing domain codes (fact categories, finding codes, health urgency, follow-up state);
* ``vet_contact_advised`` is true when the response's own rules say to contact the vet (the briefing's safety step,
  the status's vet closing line, or an escalated follow-up).

Both tools read it from the same facts (``facts_for``) with the same rules (``item_needs_safety_step``), so for the
same farm state they agree (Step 48C). Nothing here is a sentence. It is present on every successful response; an
error result carries no structuredContent.
We do not claim Alexa+ reads it: it exists so a host can surface urgency.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from clucktalk.domain.briefing import Fact, collect_facts
from clucktalk.domain.follow_up import FollowUp, FollowUpState
from clucktalk.domain.models import Farm, House
from clucktalk.domain.status import Level
from clucktalk.domain.triage import HealthCheck
from clucktalk.server.tools.follow_up import shed_health

SAFETY_LEVELS = ("OK", "WATCH", "ALERT", "UNKNOWN")
SafetyLevel = Literal["OK", "WATCH", "ALERT", "UNKNOWN"]

# The card level words of the briefing (alert / watch / info / none) and of the farm status (ok / watch / alert /
# unknown), mapped one to one. A word that is not here is a bug and raises KeyError: never a silent "OK".
_LEVEL_OF_CARD: dict[str, SafetyLevel] = {
    "ok": "OK",
    "info": "OK",
    "none": "OK",
    "watch": "WATCH",
    "alert": "ALERT",
    "unknown": "UNKNOWN",
}


class SafetyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: SafetyLevel
    reason_codes: list[str]
    vet_contact_advised: bool


def safety_from(card_level: str, reason_codes: Iterable[str], vet_contact_advised: bool) -> SafetyOut:
    """The one constructor: the level is the card's level word, the codes are unique and keep the order first seen."""
    return SafetyOut(
        level=_LEVEL_OF_CARD[card_level],
        reason_codes=list(dict.fromkeys(reason_codes)),
        vet_contact_advised=vet_contact_advised,
    )


def item_needs_safety_step(item: Any) -> bool:
    """The ONE rule for "contact your vet": a death alert, or a stored check that says urgent or a suspected reportable
    disease (the same next step). ``item`` has ``category``, ``pinned`` and ``values``."""
    if item.category in ("mortality_spike", "recent_logged_spike", "cum_mortality_high"):
        return item.pinned
    # an urgent or reportable check keeps its vet line the day after, when the follow-up item carries the check
    return item.category in ("open_health_check", "follow_up") and item.values.get("urgency") in (
        "urgent",
        "notifiable_suspect",
    )


_LEVEL_WORD_OF_FACT = {Level.ALERT: "alert", Level.WATCH: "watch", Level.OK: "info"}
_RANK: dict[str, int] = {"OK": 0, "UNKNOWN": 1, "WATCH": 1, "ALERT": 2}


def fact_items(facts: Iterable[Fact]) -> list[SimpleNamespace]:
    """Briefing facts as plain items (category, level word, pinned, values): the one input of both safety fields."""
    return [
        SimpleNamespace(
            category=f.category.value,
            level=_LEVEL_WORD_OF_FACT[f.level],
            pinned=f.pinned,
            values=f.values,
            simulated=f.simulated,
        )
        for f in facts
    ]


def facts_for(source: Any, farm: Farm, as_of: date, houses: Sequence[House] | None = None) -> tuple[Fact, ...]:
    """The briefing facts of ``houses`` (the whole farm by default) from stored data and the date: no model. The daily
    briefing and the farm status both read their safety field from this one gathering (Step 48C, part A)."""
    chosen = farm if houses is None else replace(farm, houses=tuple(houses))
    store = source.store
    checks: dict[str, HealthCheck] = {}
    recent: dict[str, tuple[HealthCheck, ...]] = {}
    handed_off: set[str] = set()
    logged: set[str] = set()
    follow_ups: dict[str, FollowUp] = {}
    for house in chosen.houses:
        health = shed_health(source, chosen.farm_id, house, as_of)
        if health.follow_up is not None and health.follow_up.state in (FollowUpState.ESCALATED, FollowUpState.DUE):
            follow_ups[house.house_id] = health.follow_up
        if health.check is not None:
            checks[house.house_id] = health.check
        recent[house.house_id] = health.recent
        handed_off |= health.handed_off
        if any(r.day == as_of for r in store.records(chosen.farm_id, house.house_id)):
            logged.add(house.house_id)
    return collect_facts(chosen, as_of, checks, frozenset(logged), recent, frozenset(handed_off), follow_ups)


def _reason_codes(items: Sequence[Any]) -> list[str]:
    codes: list[str] = []
    for item in items:
        if item.level not in ("alert", "watch"):
            continue
        codes.append(item.category)
        urgency = item.values.get("urgency")
        if urgency:
            codes.append(str(urgency))
        if item.category == "follow_up" and item.values.get("state"):
            codes.append(str(item.values["state"]))
    return codes


def briefing_safety(card_level: str, items: Sequence[Any], needs_safety_step: Callable[[Any], bool]) -> SafetyOut:
    """For the daily briefing AND the farm status, from the same facts. ``items`` are the facts as items (category,
    level, values); ``needs_safety_step`` is the one "call your vet" rule. An escalated follow-up advises the vet too
    (its sentence says "To be safe, contact your vet or doctor"). The level is the card's own level word, raised to the
    facts' level when a fact is higher (a card can only be lower than the facts for a spike logged on an earlier day
    that the status card does not show), so it is never lower than any rule."""
    codes = _reason_codes([i for i in items if not getattr(i, "simulated", False)])
    if not codes:  # a simulated item (the sale window) is a reason only when nothing else explains the level
        codes = _reason_codes(items)
    vet = any(needs_safety_step(i) for i in items) or any(
        i.category == "follow_up" and i.values.get("state") == "escalated" for i in items
    )
    out = safety_from(card_level, codes, vet)
    real = [i for i in items if not getattr(i, "simulated", False)]  # a simulated market hint never raises safety
    from_facts = "ALERT" if any(i.level == "alert" for i in real) else "WATCH" if _reason_codes(real) else "OK"
    if _RANK[from_facts] > _RANK[out.level]:
        out = out.model_copy(update={"level": from_facts})
    if out.level == "OK" and out.reason_codes:  # OK says nothing: a simulated hint on its own is not a reason
        out = out.model_copy(update={"reason_codes": []})
    return out


def status_safety(card_level: str, items: Sequence[Any], needs_safety_step: Callable[[Any], bool]) -> SafetyOut:
    """For the farm status: the same derivation as the briefing, plus the one status-only code for "no shed checked"."""
    out = briefing_safety(card_level, items, needs_safety_step)
    if card_level == "unknown":
        out = out.model_copy(update={"reason_codes": [*out.reason_codes, "no_house_checked"]})
    return out
