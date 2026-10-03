"""The structured `safety` field of the daily briefing and the farm status (review finding M6, stage 1, Step 47C).

Alexa+ composes its own speech from `structuredContent` and the tool descriptions, so the safety step must not live in
prose alone. This is the ONE place that derives the field, only from rules that already exist:

* ``level`` is the card's own level word mapped to OK / WATCH / ALERT / UNKNOWN, so it is equal to the card level by
  construction and can never be lower than the rules that set that level;
* ``reason_codes`` are the existing domain codes (fact categories, finding codes, health urgency, follow-up state);
* ``vet_contact_advised`` is true when the response's own rules say to contact the vet (the briefing's safety step,
  the status's vet closing line, or an escalated follow-up).

Nothing here is a sentence. It is present on every successful response; an error result carries no structuredContent.
We do not claim Alexa+ reads it: it exists so a host can surface urgency.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

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


def briefing_safety(card_level: str, items: Sequence[Any], needs_safety_step: Callable[[Any], bool]) -> SafetyOut:
    """For the daily briefing. ``items`` are the briefing items (category, level, values); ``needs_safety_step`` is the
    briefing's own rule for its closing "call your vet" step. An escalated follow-up advises the vet too (its sentence
    says "To be safe, contact your vet or doctor")."""
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
    vet = any(needs_safety_step(i) for i in items) or any(
        i.category == "follow_up" and i.values.get("state") == "escalated" for i in items
    )
    return safety_from(card_level, codes, vet)


def status_safety(card_level: str, houses: Sequence[Any], unavailable: Sequence[Any], vet_by_rule: bool) -> SafetyOut:
    """For the farm status (one shed or the whole farm). ``houses`` are the checked sheds (level, findings,
    follow_up, open_health_check); ``vet_by_rule`` is the status's own "needs the vet closing line" rule over every
    shed. An escalated follow-up advises the vet too."""
    codes: list[str] = []
    for h in houses:
        if h.level == "ok":
            continue
        codes += [f.code for f in h.findings if f.level != "ok"]
        if h.open_health_check is not None:
            codes += ["open_health_check", h.open_health_check.urgency]
        if h.follow_up is not None and h.follow_up.state in ("due", "escalated", "lapsed"):
            codes += ["follow_up", h.follow_up.state]
    if unavailable:
        codes.append("not_checked")
    if card_level == "unknown":
        codes.append("no_house_checked")
    vet = vet_by_rule or any(h.follow_up is not None and h.follow_up.state == "escalated" for h in houses)
    return safety_from(card_level, codes, vet)
