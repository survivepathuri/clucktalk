"""MCP App cards (docs/DESIGN.md §14): prebuilt ``ui://`` HTML resources served as ``text/html;profile=mcp-app``.

Source templates live in ``ui/cards/``; ``scripts/build_cards.py`` inlines the bundled Noto Sans Telugu font and
the fixed labels below and writes the built card next to this file. The built file is committed, so running
CluckTalk needs no Node or build step; a harness test fails if it is out of date.

Card labels are fixed bilingual strings, so they live here (not in the HTML) and go through the per-string
Telugu review (docs/TELUGU_REVIEW.md). Numbers never appear in labels: every number on a card comes from the
tool's structuredContent, the same values the spoken answer uses (docs/DESIGN.md §6, cross-modal).
"""

from __future__ import annotations

from pathlib import Path

from clucktalk.i18n import GENERIC_ERROR, GENERIC_NEXT_STEP, Text

CARDS_DIR = Path(__file__).resolve().parent
FARM_STATUS_URI = "ui://clucktalk/farm-status.html"
FARM_STATUS_FILE = CARDS_DIR / "farm_status.html"
SALE_PLAN_URI = "ui://clucktalk/sale-plan.html"
SALE_PLAN_FILE = CARDS_DIR / "sale_plan.html"

# Status is always an icon AND a word, never colour alone (docs/DESIGN.md §14).
FARM_STATUS_LABELS: dict[str, Text] = {
    "level_ok": Text("OK", "బాగుంది"),
    "level_watch": Text("WATCH", "గమనించాలి"),
    "level_alert": Text("ALERT", "శ్రద్ధ అవసరం"),
    "level_unknown": Text("UNKNOWN", "తెలియదు"),
    "farm_title": Text("Farm status", "ఫారం స్థితి"),
    "demo_badge": Text("Demo data", "డెమో డేటా"),
    "deaths_today": Text("Deaths today", "ఈరోజు మరణాలు"),
    "deaths_latest": Text("Deaths, latest count", "తాజా లెక్కలో మరణాలు"),
    "feed_left": Text("Feed stock", "ఫీడ్ నిల్వ"),
    "feed_days": Text("Feed stock, days", "ఫీడ్ నిల్వ, రోజులు"),
    "not_known": Text("not known", "తెలియదు"),
    "avg_weight": Text("Average weight", "సగటు బరువు"),
    "laying": Text("Laying", "గుడ్ల ఉత్పత్తి"),
    # Templates: the card replaces {n} with a value from structuredContent, formatted like the spoken answer.
    "days_n": Text("{n} days", "{n} రోజులు"),
    "day_one_n": Text("{n} day", "{n} రోజు"),
    "at_least_days_n": Text("at least {n} days", "కనీసం {n} రోజులు"),
    "grams_n": Text("{n} g", "{n} గ్రా."),
    "target_grams_n": Text("target {n} g", "లక్ష్యం {n} గ్రా."),
    "birds_n": Text("{n} birds", "{n} కోళ్లు"),
    "age_day_n": Text("Day {n}", "{n}వ రోజు"),
    "readings_from_d": Text("Latest readings: {d}", "తాజా రీడింగులు: {d}"),  # {d}: a date, dd-mm-yyyy
    "tap_hint": Text("Tap a shed for details", "వివరాల కోసం షెడ్‌ను తాకండి"),
    "back_all": Text("All sheds", "అన్ని షెడ్లు"),
    "not_checked": Text("Could not check", "తనిఖీ చేయలేకపోయాను"),
    "loading": Text("Loading", "లోడ్ అవుతోంది"),
    "sorry": Text("Sorry", "క్షమించండి"),
    "generic_error": GENERIC_ERROR,  # already reviewed strings, reused (card-side failure of a tap)
    "generic_next": GENERIC_NEXT_STEP,
}


def farm_status_html() -> str:
    """The built farm-status card. Missing file = broken checkout: fail loud at startup (Rule 6)."""
    if not FARM_STATUS_FILE.exists():
        raise RuntimeError(f"{FARM_STATUS_FILE} is missing. Rebuild it: .venv\\Scripts\\python scripts\\build_cards.py")
    return FARM_STATUS_FILE.read_text(encoding="utf-8")


# Sell-day plan card (docs/DESIGN.md §12.4): a simple per-day bar chart, best day highlighted, break-even marked.
SALE_PLAN_LABELS: dict[str, Text] = {
    "sale_title": Text("Sell-day plan", "అమ్మకం రోజు ప్రణాళిక"),
    "demo_badge": Text("Demo data", "డెమో డేటా"),
    "simulated_price": Text("Simulated price", "అంచనా ధర (డెమో)"),
    "best_day": Text("Best day", "మంచి రోజు"),
    "today": Text("Today", "ఈరోజు"),
    "break_even": Text("Break-even", "బ్రేక్-ఈవెన్"),
    "net_vs_today": Text("Net vs today", "ఈరోజుతో పోలిస్తే నికరం"),
    "weight": Text("Weight", "బరువు"),
    "fcr": Text("FCR", "FCR"),
    "growing_charge": Text("Growing charge", "గ్రోయింగ్ ఛార్జ్"),
    "no_terms_hint": Text(
        "Save your contract terms to see the growing charge", "గ్రోయింగ్ ఛార్జ్ చూడాలంటే మీ కాంట్రాక్ట్ నిబంధనలు సేవ్ చేయండి"
    ),
    "grams_n": Text("{n} g", "{n} గ్రా."),
    "sorry": Text("Sorry", "క్షమించండి"),
    "generic_error": GENERIC_ERROR,
    "generic_next": GENERIC_NEXT_STEP,
    "loading": Text("Loading", "లోడ్ అవుతోంది"),
}


def sale_plan_html() -> str:
    """The built sale-plan card. Missing file = broken checkout: fail loud at startup (Rule 6)."""
    if not SALE_PLAN_FILE.exists():
        raise RuntimeError(f"{SALE_PLAN_FILE} is missing. Rebuild it: .venv\\Scripts\\python scripts\\build_cards.py")
    return SALE_PLAN_FILE.read_text(encoding="utf-8")
