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

from clucktalk.domain.feed import BAG_KG

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

# Daily briefing (docs/DESIGN.md §18): "today's briefing" reads the top 3; a bare "more" reads the rest. A shed in the
# sentence means the farmer asked about that shed (or a health check), not the whole-farm briefing.
BRIEFING = re.compile(r"\b(?:briefing|daily update|morning update)\b")
BRIEFING_MORE = re.compile(r"^(?:more|tell me more|what else|anything else|aur batao)$")

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
# Sale-day plan (docs/DESIGN.md §12.4). "rate is 95" carries a farmer-given live price to plan_sale.
SELL = re.compile(r"\b(?:sell|selling|bech|bech do|bechna|bechu|kab bechun|kab bechu)\b")
RATE_VALUE = re.compile(r"\b(?:rate is|rate|market rate is|market rate|price is|price)\s+(\d+(?:\.\d+)?)\b")
STATUS = re.compile(
    r"\b(?:how(?:'s| is| are)?|status|doing|kaisa|kaise|kaisi|haal|check|update|report|going|problem)\b"
)
WHOLE_FARM = re.compile(r"\b(?:farm|all (?:shed|house)s?|every (?:shed|house)|everything)\b")

# Voice record book (docs/DESIGN.md §13.2, §5.1). "record fields" (deaths, feed given, a weight sample, a
# medicine/vaccine given) require a house, same as log_daily_record itself; a stated number is what tells a
# *report* ("2 bags of feed for shed 2") apart from a *question* (FEED above, "how much feed does shed 2 need").
RECORD_BOOK = re.compile(
    r"\b(?:record book|record summary|records? summary|who(?:'s| has| have)? logged|what(?:'s| is)? logged"
    r"|record status|today'?s records?)\b"
)
DEATHS_WORD = r"(?:died|dead|deaths?|mar gaye|mare|marre?)"
NO_DEATHS = re.compile(rf"\b(?:no|zero|none)\s+{DEATHS_WORD}\b")
# The word-then-number order only counts when that number isn't really another field's (a negative lookahead,
# so "no deaths, 3 bags of feed" doesn't read the 3 as a death count).
DEATHS_VALUE = re.compile(
    rf"\b(\d+)\s*(?:birds?|chickens?)?\s*{DEATHS_WORD}\b"
    rf"|\b{DEATHS_WORD}\b[\w\s]{{0,15}}?(\d+)\b(?!\s*(?:bags?|bori|g|grams?))"
)
FEED_GIVEN_BAGS = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:bags?|bori)\b")
# DESIGN.md §13.2 lists "feed used (bags or kg)": a farmer who says kg is converted to bags here (the tool's own
# contract stays bags-only, matching plan_feed's convention) rather than falling through to plan_feed unheard
# (Rule 11 review 2026-09-29: "50 kg" previously matched only the generic FEED trigger below and silently
# became a feed *question*, dropping the farmer's report).
FEED_GIVEN_KG = re.compile(r"\b(\d+(?:\.\d+)?)\s*kg\b")
WEIGHT_VALUE = re.compile(r"\b(\d+(?:\.\d+)?)\s*g(?:ram)?s?\b")
WEIGHT_SAMPLE_BIRDS = re.compile(
    r"\b(\d+)\s*(?:birds?|chickens?)\s*weighed\b|\bweighed\s*(?:only\s+)?(\d+)\s*(?:birds?|chickens?)\b"
)
TREATMENT_STOPWORDS = {"the", "a", "an", "this", "that", "its", "gave", "given", "give", "got", "with"}
# A dose-shaped word (unit or bare number) right before the kind word means a dose was said where a name
# should be — never guessed as if it were the treatment's name (Rule 11 review 2026-09-29: "gave 5 ml vaccine"
# previously stored name="Ml").
TREATMENT_DOSE_WORDS = {"ml", "mg", "mcg", "cc", "iu", "units", "unit", "kg", "g", "gram", "grams"}
# Up to two words before the kind word (e.g. "Newcastle disease vaccine"), never crossing into the kind word.
TREATMENT_VALUE = re.compile(
    r"\b((?:[a-z][\w'-]*\s+){0,2}[a-z][\w'-]*)\s+(?P<kind>vaccine|teeka|tika|medicine|dawai)\b"
)
VACCINE_WORDS = {"vaccine", "teeka", "tika"}


def _treatment_name(raw: str) -> str | None:
    tokens = [t for t in raw.split() if t not in TREATMENT_STOPWORDS]
    if not tokens or any(t.isdigit() or t in TREATMENT_DOSE_WORDS for t in tokens):
        return None  # nothing left, or a dose fragment where a name should be: never guess
    return " ".join(tokens).title()


def record_fields(text: str, house: str | None) -> tuple[dict, list[str]]:
    """Whichever of deaths / feed_bags / a weight sample / a treatment ``text`` reports, and which rule(s)
    matched (for the developer panel). The house phrase is stripped first so its own number is never mistaken
    for a reported count (docs/DESIGN.md §5 rule 2: one utterance, all fields)."""
    remainder = text.replace(house, " ", 1) if house else text
    fields: dict = {}
    matched: list[str] = []
    if NO_DEATHS.search(remainder):
        fields["deaths"] = 0
        matched.append("deaths")
    else:
        deaths = DEATHS_VALUE.search(remainder)
        if deaths:
            fields["deaths"] = int(deaths.group(1) or deaths.group(2))
            matched.append("deaths")
    feed_bags = FEED_GIVEN_BAGS.search(remainder)
    if feed_bags:
        fields["feed_bags"] = float(feed_bags.group(1))
        matched.append("feed given")
    else:
        feed_kg = FEED_GIVEN_KG.search(remainder)
        if feed_kg:
            fields["feed_bags"] = round(float(feed_kg.group(1)) / BAG_KG, 2)
            matched.append("feed given (kg)")
    weight = WEIGHT_VALUE.search(remainder)
    if weight:
        # Sent even without a bird count: the tool itself then asks for one (WeightSampleNeedsBirdCount) rather
        # than the host silently dropping the report by not matching any record intent at all (Rule 11 review
        # 2026-09-29: a weight alone used to fall through to an unrelated status query).
        fields["avg_weight_g"] = float(weight.group(1))
        matched.append("weight sample")
        sample = WEIGHT_SAMPLE_BIRDS.search(remainder)
        if sample:
            fields["weight_sample_birds"] = int(sample.group(1) or sample.group(2))
    treatment = TREATMENT_VALUE.search(remainder)
    if treatment:
        name = _treatment_name(treatment.group(1))
        if name:
            kind = "vaccine" if treatment.group("kind") in VACCINE_WORDS else "medicine"
            fields["treatments"] = [{"kind": kind, "name": name}]
            matched.append("treatment given")
    return fields, matched


# Health triage (docs/DESIGN.md §18): farmer words -> the closed list of signs start_health_check accepts. The
# farmer's whole utterance also goes along as `symptoms` (prompt data for the agent, never spoken back).
SIGN_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("coughing", re.compile(r"\b(?:cough\w*|khansi|khaansi|khasi)\b")),
    ("sneezing", re.compile(r"\b(?:sneez\w*|chheenk\w*|cheenk\w*)\b")),
    ("gasping", re.compile(r"\b(?:gasp\w*|breathing (?:hard|problem)|saans)\b")),
    ("nasal_discharge", re.compile(r"\b(?:runny nose|nasal discharge|naak beh\w*)\b")),
    ("swollen_head", re.compile(r"\b(?:swollen (?:heads?|face|eyes)|swelling|head swell\w*|sujan)\b")),
    (
        "discoloured_comb",
        re.compile(r"\b(?:(?:blue|purple|black) (?:combs?|wattles?|legs?)|combs? (?:is |are )?(?:blue|purple))\b"),
    ),
    ("twisted_neck", re.compile(r"\b(?:twist\w* necks?|necks? twist\w*|gardan (?:mud\w*|tedhi))\b")),
    ("paralysis", re.compile(r"\b(?:paraly\w*|drooping wings?|wings? drooping|legs? not working)\b")),
    ("diarrhoea", re.compile(r"\b(?:diarr?h?o?ea|loose droppings|dast|patli beet)\b")),
    ("not_eating", re.compile(r"\b(?:not eating|stopped eating|off feed|khana nahi\w*|dana nahi\w*)\b")),
    ("dull", re.compile(r"\b(?:dull|huddl\w*|sust|lazy)\b")),
    ("lame", re.compile(r"\b(?:lame\w*|limp\w*|langd\w*)\b")),
    ("panting", re.compile(r"\b(?:panting|pant|hanf\w*)\b")),
    ("sudden_deaths", re.compile(r"\b(?:dying suddenly|suddenly dying|sudden deaths?|died suddenly|achanak mar\w*)\b")),
)
HEALTH_RESULT = re.compile(
    r"\b(?:health check|check (?:is )?ready|what did (?:the|my) (?:health )?check|triage result|jaanch)\b"
)
VET_HANDOFF = re.compile(r"\b(?:send|bhej\w*)\b.*\b(?:vet|doctor|daktar)\b|\b(?:vet|doctor)\b.*\bbhej\w*\b")


# "no sudden deaths", "not coughing", "without any coughing": the word right before a sign negates it. Only that
# direct form counts ("no more coughing" keeps the sign), so a real sign is never dropped on a guess (Rule 11
# review 2026-09-30: "no sudden deaths, just coughing" used to report sudden deaths).
NEGATED_BEFORE = re.compile(r"\b(?:no|not|without|never|nahi|nahin)\s+(?:any\s+)?$")


def health_signs(text: str) -> list[str]:
    return [
        sign
        for sign, pattern in SIGN_WORDS
        if any(not NEGATED_BEFORE.search(text[: m.start()]) for m in pattern.finditer(text))
    ]


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
    if BRIEFING_MORE.match(text):
        return Intent("get_daily_briefing", {"more": True}, "briefing: 'more' / 'what else'")
    if BRIEFING.search(text) and not house_phrase(text):
        return Intent("get_daily_briefing", {}, "briefing: 'briefing' / 'daily update'")
    if RECORD_BOOK.search(text):
        return Intent("get_record_book", {}, "record book: 'record book' / 'who's logged' / 'what's logged'")
    house = house_phrase(text)
    args = {"house": house} if house else {}
    signs = health_signs(text)
    if house and signs:
        # Signs of illness come first: a sick-bird report must never become a silent log, a "get result" or a
        # vet send without its check (Rule 11 review 2026-09-29).
        rule = "health: signs (" + ", ".join(signs) + ") + shed"
        return Intent("start_health_check", {**args, "signs": signs, "symptoms": utterance.strip()[:300]}, rule)
    if house and VET_HANDOFF.search(text):
        return Intent("prepare_vet_handoff", args, "vet handoff: 'send ... vet' / 'vet ko bhej' + shed")
    if house and HEALTH_RESULT.search(text):
        return Intent("get_health_check", args, "health result: 'health check' / 'check ready' + shed")
    if house:
        fields, matched = record_fields(text, house)
        if fields:
            rule = "record: " + ", ".join(matched) + " + shed"
            return Intent("log_daily_record", {**args, **fields}, rule)
    if SELL.search(text) or RATE_VALUE.search(text):
        sale_args = dict(args)
        rate = RATE_VALUE.search(text)
        if rate:
            sale_args["live_price_per_kg"] = float(rate.group(1))
        rule = "sell: 'sell' / 'bech' / 'kab bechun'" + (" + rate" if rate else "") + (" + shed" if house else "")
        return Intent("plan_sale", sale_args, rule)
    if FEED.search(text):
        return Intent("plan_feed", args, "feed: 'feed' / 'dana' / 'bags' / 'stock'" + (" + shed" if house else ""))
    if house:
        return Intent("get_farm_status", args, "status: shed mentioned")
    if STATUS.search(text) or WHOLE_FARM.search(text):
        return Intent("get_farm_status", {}, "status: 'how is' / 'farm' (no shed: whole farm)")
    return None
