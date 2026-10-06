"""Rule-based Telugu understanding for the pilot page (Step 51 part C). Typed Telugu only: the farmer's keyboard does
the voice typing, so this module sees text, never audio.

At most 8 actions: log deaths for a shed, today's status, the briefing, a health check, a sale plan, how a shed is after
a check (better, same, worse), yes or no to a read-back, and help. Everything else is "not understood" and the page then
shows the chips. Rules, in plain view:

* the text is NFC-normalised, Telugu digits become ASCII digits, and only U+0C00 to U+0C7F, ASCII letters and digits are
  kept; it is split on spaces (never on ``\\b``, which cuts Telugu words at their vowel signs);
* a shed is a shed word plus ONE number next to it (the shed word then a digit or a number word, or an ordinal before
  the shed word); the server resolves it;
* a number that cannot be read as one number (two numbers side by side, a compound that makes no sense, more than
  100000) is never guessed: no number means "ask again", an unreadable one means "not understood";
* a health check never reads signs from free text: it only opens the sign buttons (chips only, Step 51 decision D4);
* a yes or a no counts only as the whole message.
Nothing here writes: a tool that changes something is always read back and confirmed first (the server's proposal flow,
or the host's own read-back for a health check).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from clucktalk.domain.triage import Sign
from clucktalk.simulator.intents import Intent

MAX_TEXT = 500
MAX_NUMBER = 100_000
MAX_HOUSE = 99


class Chip(StrEnum):
    DEATHS = "deaths"
    NO_DEATHS = "no_deaths"
    STATUS = "status"
    BRIEFING = "briefing"
    HEALTH = "health"
    SALE = "sale"
    FOLLOW_UP = "follow_up"
    HELP = "help"


_WORDS = json.loads((Path(__file__).with_name("telugu_words.json")).read_text(encoding="utf-8"))
# The matching vocabulary lives in telugu_words.json: it is what the rules look for, not words shown to the farmer,
# so it is not part of the Telugu review list. Numbers: UNITS, TEENS, TENS, HUNDREDS, THOUSANDS, ORDINALS.
UNITS: dict[str, int] = _WORDS["UNITS"]
TEENS: dict[str, int] = _WORDS["TEENS"]
TENS: dict[str, int] = _WORDS["TENS"]
HUNDREDS = set(_WORDS["HUNDREDS"])
THOUSANDS = set(_WORDS["THOUSANDS"])
ORDINALS: dict[str, int] = _WORDS["ORDINALS"]
SUFFIXES = tuple(_WORDS["SUFFIXES"])  # a number word may carry one case suffix (the word for "two" + "in")
SHED_STEMS = tuple(_WORDS["SHED_STEMS"])
YES = set(_WORDS["YES"])
NO = set(_WORDS["NO"])
DEATH_STEMS = tuple(_WORDS["DEATH_STEMS"])
NEGATIVE_DEATHS = tuple(_WORDS["NEGATIVE_DEATHS"])
NEGATION_WORDS = set(_WORDS["NEGATION_WORDS"])
HELP_STEMS = tuple(_WORDS["HELP_STEMS"])
CAN_DO = tuple(_WORDS["CAN_DO"])
BRIEFING_WORDS = tuple(_WORDS["BRIEFING_WORDS"])
HEALTH_WORDS = tuple(_WORDS["HEALTH_WORDS"])
SALE_STEMS = tuple(_WORDS["SALE_STEMS"])
RATE_WORDS = set(_WORDS["RATE_WORDS"])
STATUS_STEMS = tuple(_WORDS["STATUS_STEMS"])
FARM_WORDS = tuple(_WORDS["FARM_WORDS"])
BETTER = tuple(_WORDS["BETTER"])
SAME = tuple(_WORDS["SAME"])
WORSE = tuple(_WORDS["WORSE"])
ADD = set(_WORDS["ADD"])
REPLACE = set(_WORDS["REPLACE"])
WHAT = set(_WORDS["WHAT"])
HEALTH_ADJ = set(_WORDS["HEALTH_ADJ"])
WELL = set(_WORDS["WELL"])
WORD_VALUES = {**UNITS, **TEENS, **TENS}

OUTCOMES = ("better", "same", "worse")
_TELUGU_DIGITS = {0x0C66 + i: str(i) for i in range(10)}  # U+0C66 to U+0C6F
_TELUGU_BLOCK = f"{chr(0x0C00)}-{chr(0x0C7F)}"  # U+0C00 to U+0C7F
_TOKEN = re.compile(rf"\d+|[{_TELUGU_BLOCK}]+|[a-z']+")
_NOT_KEPT = re.compile(rf"[^\w\s'{_TELUGU_BLOCK}]", re.UNICODE)


def normalise_te(text: str) -> str:
    """NFC, no invisible formatting characters (zero-width joiners are common in Telugu typing), Telugu digits as ASCII
    digits, punctuation as a space, lower case, single spaces. Vowel signs are kept."""
    text = unicodedata.normalize("NFC", text[:MAX_TEXT])
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.translate(_TELUGU_DIGITS).lower()
    text = _NOT_KEPT.sub(" ", text.replace("_", " "))
    return " ".join(text.split())


def tokens_of(text: str) -> list[str]:
    return _TOKEN.findall(normalise_te(text))


# -- numbers ---------------------------------------------------------------------------------------------------------


def _word(token: str) -> str | None:
    """The number word in ``token``, with one case suffix taken off if needed, else None."""
    known = set(WORD_VALUES) | HUNDREDS | THOUSANDS
    if token in known:
        return token
    for suffix in SUFFIXES:
        if token.endswith(suffix) and token[: -len(suffix)] in known:
            return token[: -len(suffix)]
    return None


def is_number_token(token: str) -> bool:
    return token.isdecimal() or _word(token) is not None


def parse_number(tokens: list[str]) -> int | None:
    """One number from ``tokens``, or None. Digits stand alone (two digit tokens are two numbers); words add up like
    twenty five = 25, hundred twenty = 120, two hundreds fifty = 250, two thousands = 2000 (the Telugu words are in
    telugu_words.json). A pair that is not a number (two units, a ten then a ten, a ten then hundreds) is None, never a
    guess."""
    if not tokens:
        return None
    if any(t.isdecimal() for t in tokens):
        if len(tokens) != 1 or len(tokens[0]) > 7:
            return None
        value = int(tokens[0])
        return value if value <= MAX_NUMBER else None
    thousands, hundreds, below = 0, 0, 0
    seen_thousand = seen_hundred = False
    for raw in tokens:
        word = _word(raw)
        if word is None:
            return None
        if word in WORD_VALUES:
            value = WORD_VALUES[word]
            if len(tokens) > 1 and value == 0:
                return None
            if below and not (below in TENS.values() and 1 <= value <= 9):
                return None  # only a ten may be followed by a unit
            below += value
        elif word in HUNDREDS:
            if seen_hundred or below not in range(0, 10):
                return None
            hundreds, below, seen_hundred = (below or 1) * 100, 0, True
        else:
            if seen_thousand or (below not in range(0, 10) and not (hundreds or below)):
                return None
            if below >= 10 and not hundreds:
                return None
            part = hundreds + below
            thousands, hundreds, below, seen_thousand = (part or 1) * 1000, 0, 0, True
            seen_hundred = False
    total = thousands + hundreds + below
    return total if total <= MAX_NUMBER else None


def _number_runs(tokens: list[str]) -> list[list[str]]:
    """Maximal runs of number words (a digit token is a run of its own)."""
    runs: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok.isdecimal():
            if current:
                runs.append(current)
                current = []
            runs.append([tok])
        elif is_number_token(tok):
            current.append(tok)
        else:
            if current:
                runs.append(current)
                current = []
    if current:
        runs.append(current)
    return runs


# -- the shed --------------------------------------------------------------------------------------------------------


def _is_shed(token: str) -> bool:
    return token.startswith(SHED_STEMS)


def _house_from(tokens: list[str]) -> tuple[int | None, set[int]]:
    """The shed number and the token positions it used. An ordinal before the shed word wins; else the ONE number
    token right after it (a digit or a number word). Never more than one token, never above 99."""
    for i, tok in enumerate(tokens):
        if not _is_shed(tok):
            continue
        if i > 0 and tokens[i - 1] in ORDINALS:
            return ORDINALS[tokens[i - 1]], {i - 1, i}
        if i + 1 < len(tokens) and is_number_token(tokens[i + 1]):
            value = parse_number([tokens[i + 1]])
            word = _word(tokens[i + 1])
            if value is None and word is not None:
                value = WORD_VALUES.get(word)
            if value is not None and 1 <= value <= MAX_HOUSE:
                return value, {i, i + 1}
        return None, {i}
    return None, set()


# -- the actions -----------------------------------------------------------------------------------------------------


def _has(tokens: list[str], stems: tuple[str, ...]) -> bool:
    return any(t.startswith(stems) for t in tokens)


@dataclass(frozen=True)
class TeResult:
    kind: str  # "intent" | "choose" | "yes" | "no" | "none"
    intent: Intent | None = None
    chip: Chip | None = None  # "choose": the buttons to show next
    params: dict[str, Any] = field(default_factory=dict)  # "choose": what was already understood
    rule: str = ""


NONE = TeResult("none", rule="not understood")


def yes_no_te(text: str) -> str | None:
    """'yes' or 'no' only when the whole message is one explicit answer."""
    norm = normalise_te(text)
    if norm in YES:
        return "yes"
    if norm in NO:
        return "no"
    return None


def choice_te(text: str) -> str | None:
    """ "add" or "replace" only when the whole message is that one word (the answer to the add-or-replace question)."""
    norm = normalise_te(text)
    if norm in ADD:
        return "add"
    if norm in REPLACE:
        return "replace"
    return None


def _house_arg(number: int) -> str:
    return f"shed {number}"


def match_te(text: str) -> TeResult:
    """What the typed Telugu means. Total: never raises."""
    try:
        return _match(text)
    except (ValueError, IndexError, KeyError, TypeError):  # a bug here must be "not understood", never a crash
        return NONE


def _match(text: str) -> TeResult:  # noqa: C901 - one flat list of rules, in order
    answer = yes_no_te(text)
    if answer is not None:
        return TeResult(answer, rule=f"answer: {answer}")
    tokens = tokens_of(text)
    if not tokens:
        return NONE
    if _has(tokens, HELP_STEMS) or (_has(tokens, CAN_DO) and any(t in WHAT for t in tokens)):
        return TeResult("intent", Intent("get_help", {}, "help (Telugu)"), rule="help")
    house, used = _house_from(tokens)
    house_given = any(_is_shed(t) for t in tokens)
    if _has(tokens, BRIEFING_WORDS) and not house_given:
        return TeResult("intent", Intent("get_daily_briefing", {}, "briefing (Telugu)"), rule="briefing")
    if _has(tokens, HEALTH_WORDS) and any(t in HEALTH_ADJ for t in tokens):
        return TeResult(
            "choose", chip=Chip.HEALTH, params={} if house is None else {"house": house}, rule="health: chips only"
        )
    rest = [t for i, t in enumerate(tokens) if i not in used]
    has_death = _has(tokens, DEATH_STEMS)
    if has_death:
        zero = _has(tokens, NEGATIVE_DEATHS) or (any(t in NEGATION_WORDS for t in tokens) and _has(tokens, DEATH_STEMS))
        runs = _number_runs(rest)
        if zero and not runs:
            count: int | None = 0
        elif len(runs) == 1:
            count = parse_number(runs[0])
            if count is None:
                return NONE  # a number that cannot be read: never guessed
        elif len(runs) == 0:
            count = None
        else:
            return NONE  # two numbers: unclear which is which
        if zero and runs:
            return NONE  # "no deaths" together with a number contradicts itself
        if house is None or count is None:
            params: dict[str, Any] = {}
            if house is not None:
                params["house"] = house
            if count is not None:
                params["count"] = count
            return TeResult("choose", chip=Chip.DEATHS, params=params, rule="deaths: asks for what is missing")
        return TeResult(
            "intent",
            Intent("log_daily_record", {"house": _house_arg(house), "deaths": count}, "deaths (Telugu)"),
            rule="deaths",
        )
    outcome = _outcome(tokens)
    if outcome is not None:
        if house is None:
            return TeResult("choose", chip=Chip.FOLLOW_UP, params={"outcome": outcome}, rule="follow-up: which shed")
        args = {"house": _house_arg(house), "outcome": outcome}
        return TeResult("intent", Intent("report_health_follow_up", args, "follow-up (Telugu)"), rule="follow-up")
    if _has(tokens, SALE_STEMS):
        args = {} if house is None else {"house": _house_arg(house)}
        for i, tok in enumerate(rest[:-1]):
            if tok in RATE_WORDS and rest[i + 1].isdecimal():
                price = parse_number([rest[i + 1]])
                if price is None:
                    return NONE
                args["live_price_per_kg"] = float(price)
        return TeResult("intent", Intent("plan_sale", args, "sale (Telugu)"), rule="sale")
    if house is not None or _has(tokens, STATUS_STEMS) or _has(tokens, FARM_WORDS):
        asks = _has(tokens, STATUS_STEMS) or _has(tokens, FARM_WORDS)
        if house is None and not asks:
            return NONE
        if house is not None and not asks and _number_runs(rest):
            return NONE  # a shed and a stray number (a weight, a count of something): never read as "how is it"
        args = {} if house is None else {"house": _house_arg(house)}
        return TeResult("intent", Intent("get_farm_status", args, "status (Telugu)"), rule="status")
    return NONE


def _outcome(tokens: list[str]) -> str | None:
    """better / same / worse. "Not well" (the Telugu for it) is never "better": it is read as "same"."""
    if _has(tokens, WORSE):
        return "worse"
    negated = any(t in WELL for t in tokens) and any(t in NEGATION_WORDS for t in tokens)
    if negated:
        return "same"
    if _has(tokens, SAME):
        return "same"
    if _has(tokens, BETTER):
        return "better"
    return None


# -- chips -----------------------------------------------------------------------------------------------------------
def _int(value: Any, low: int, high: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be a whole number from {low} to {high}")
    return value


def chip_intent(chip: str, params: dict[str, Any]) -> Intent:
    """The intent for a tapped chip. Strict: anything unexpected raises ValueError (the page never sends it). Chips
    never go through the text matcher."""
    kind = Chip(chip)  # ValueError for an unknown chip
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    allowed = {
        Chip.STATUS: {"house"},
        Chip.BRIEFING: set(),
        Chip.SALE: {"house"},
        Chip.HELP: set(),
        Chip.DEATHS: {"house", "count"},
        Chip.NO_DEATHS: {"house"},
        Chip.HEALTH: {"house", "signs"},
        Chip.FOLLOW_UP: {"house", "outcome"},
    }[kind]
    extra = set(params) - allowed
    if extra:
        raise ValueError(f"unexpected parameter(s) {sorted(extra)}")
    house = _house_arg(_int(params["house"], 1, MAX_HOUSE, "house")) if "house" in params else None
    head = {} if house is None else {"house": house}
    rule = f"chip: {kind.value}"
    match kind:
        case Chip.BRIEFING:
            return Intent("get_daily_briefing", {}, rule)
        case Chip.HELP:
            return Intent("get_help", {}, rule)
        case Chip.STATUS:
            return Intent("get_farm_status", head, rule)
        case Chip.SALE:
            return Intent("plan_sale", head, rule)
    if house is None:
        raise ValueError("house is required")
    match kind:
        case Chip.NO_DEATHS:
            return Intent("log_daily_record", {"house": house, "deaths": 0}, rule)
        case Chip.DEATHS:
            return Intent(
                "log_daily_record", {"house": house, "deaths": _int(params.get("count"), 0, MAX_NUMBER, "count")}, rule
            )
        case Chip.FOLLOW_UP:
            if params.get("outcome") not in OUTCOMES:
                raise ValueError("outcome must be better, same or worse")
            return Intent("report_health_follow_up", {"house": house, "outcome": params["outcome"]}, rule)
        case _:
            signs = params.get("signs")
            valid = {s.value for s in Sign}
            if not isinstance(signs, list) or not signs or len(set(signs)) != len(signs) or not set(signs) <= valid:
                raise ValueError("signs must be a non-empty list of different known signs")
            return Intent("start_health_check", {"house": house, "signs": list(signs), "symptoms": ""}, rule)
