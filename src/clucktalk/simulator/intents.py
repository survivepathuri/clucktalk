"""Mock host language understanding: a deterministic, rule-based intent matcher (demo mode only).

In Alexa+, the host's LLM picks the tool. The Simulator's mock mode replaces that with visible rules, so the
demo runs offline and every decision can be traced in the developer panel (the matched rule is returned).
It only extracts *which* shed was mentioned and passes those words on unchanged: resolving "shed two",
"kotam do", "second shed" to a house is the MCP server's job (clucktalk.domain.houses), so an unknown shed gets
the server's safe error, never a guess here.
A bare "yes" / "no" is not an intent: the host sends it only as the answer to a pending read-back
(clucktalk.simulator.app, docs/DESIGN.md §5.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HOUSE_NOUN = r"(?:shed|house|kotam|kottam|kotham|coop)"
NUMBER = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|ek|do|teen|char|chaar|paanch|panch)"
ORDINAL = r"(?:first|second|third|fourth|fifth)"
# "shed 2", "shed number two", "house no 3", "kotam do" | "second shed" | "do number shed", "teen shed"
HOUSE_PATTERNS = (
    re.compile(rf"\b{HOUSE_NOUN}\s+(?:no\s+|number\s+)?{NUMBER}\b"),
    re.compile(rf"\b{ORDINAL}\s+{HOUSE_NOUN}\b"),
    re.compile(rf"\b{NUMBER}\s+(?:number\s+)?{HOUSE_NOUN}\b"),
)
# Speech recognisers often hear "shed" as one of these; normalise before matching.
MISHEARD = {"shade": "shed", "shred": "shed", "shared": "shed", "sheds": "shed", "houses": "house"}
WAKE = re.compile(r"^(?:alexa\s*)?(?:(?:ask|tell|open)\s+clucktalk\s*(?:to|for|if|about|whether|how)?\s*)?")

HELP = re.compile(r"\b(?:what can (?:you|clucktalk) do|help me|^help$|what do you do|how do i use)\b")
# Farm mode (docs/DESIGN.md §13.1). The words that pick the mode; the server declares the same synonyms.
CONTRACT_WORDS = r"(?:contract|integration|integrator|company|agreement)"
INDEPENDENT_WORDS = r"(?:independent|own farm(?:ing)?|apna farm|khud ka farm)"  # "own shed 2" is not a mode
# "we're not a contract farm", "don't switch": never start a switch from a negated sentence.
NEGATION = re.compile(r"\b(?:not|don't|dont|do not|never|nahi|nahin|no longer)\b")
MODE_SWITCH = re.compile(
    rf"\b(?:switch|change|set|make|convert|move|turn)\b.*\b(?P<mode>{CONTRACT_WORDS}|{INDEPENDENT_WORDS})\b"
    rf"|\b(?:we are|i am|i'm|we're|this is)\b.*\b(?P<mode2>{CONTRACT_WORDS}|{INDEPENDENT_WORDS})\b.*\bfarm"
)
PROFILE = re.compile(
    r"\b(?:what kind of farm|what type of farm|farm type|contract or independent|independent or contract"
    r"|am i (?:a |an )?(?:contract|independent)|is (?:my|this) farm (?:contract|independent)|farm profile)\b"
)
# A whole utterance that answers a read-back (docs/DESIGN.md §5.1). Only these words count as an explicit answer.
YES = re.compile(r"^(?:yes|yeah|yep|yes please|haan|haan ji|ji haan|han ji|avunu|confirm|yes confirm)$")
NO = re.compile(r"^(?:no|nope|no thanks|nahi|nahin|na|vaddu|cancel|don't|do not)$")
FEED = re.compile(r"\b(?:feed|dana|daana|bags?|bori|stock|reorder)\b")
STATUS = re.compile(
    r"\b(?:how(?:'s| is| are)?|status|doing|kaisa|kaise|kaisi|haal|check|update|report|going|problem)\b"
)
WHOLE_FARM = re.compile(r"\b(?:farm|all (?:shed|house)s?|every (?:shed|house)|everything)\b")


@dataclass(frozen=True)
class Intent:
    tool: str
    arguments: dict = field(default_factory=dict)
    rule: str = ""  # which rule matched; shown in the developer panel


def normalise(utterance: str) -> str:
    text = utterance.lower().replace("cluck talk", "clucktalk").replace("click talk", "clucktalk")
    text = re.sub(r"[^\w\s']", " ", text)
    text = " ".join(MISHEARD.get(w, w) for w in text.split())
    return WAKE.sub("", text).strip()


def house_phrase(text: str) -> str | None:
    for pattern in HOUSE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def yes_no(utterance: str) -> str | None:
    """'yes' or 'no' when the whole utterance is an explicit answer; None otherwise ("yes, and shed two?" is not)."""
    text = normalise(utterance)
    if YES.match(text):
        return "yes"
    if NO.match(text):
        return "no"
    return None


def match(utterance: str) -> Intent | None:
    """The tool to call for ``utterance``, or None when no rule applies (the host then says what it can do)."""
    text = normalise(utterance)
    if not text:
        return None
    if HELP.search(text):
        return Intent("get_help", {}, "help: 'what can you do' / 'help'")
    switch = None if NEGATION.search(text) else MODE_SWITCH.search(text)
    if switch:
        word = switch.group("mode") or switch.group("mode2")
        mode = "contract" if re.fullmatch(CONTRACT_WORDS, word) else "independent"
        return Intent("set_farm_mode", {"mode": mode}, f"farm mode: 'switch/change ... {word}'")
    if NEGATION.search(text) and re.search(rf"\b(?:{CONTRACT_WORDS}|{INDEPENDENT_WORDS})\b", text):
        return None  # a negated mode sentence is unclear: the host asks again rather than guessing
    if PROFILE.search(text):
        return Intent("get_farm_profile", {}, "farm mode: 'what kind of farm' / 'contract or independent'")
    house = house_phrase(text)
    args = {"house": house} if house else {}
    if FEED.search(text):
        return Intent("plan_feed", args, "feed: 'feed' / 'dana' / 'bags' / 'stock'" + (" + shed" if house else ""))
    if house:
        return Intent("get_farm_status", args, "status: shed mentioned")
    if STATUS.search(text) or WHOLE_FARM.search(text):
        return Intent("get_farm_status", {}, "status: 'how is' / 'farm' (no shed: whole farm)")
    return None
