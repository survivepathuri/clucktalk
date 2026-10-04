"""Fixed bilingual strings (docs/DESIGN.md §8). Telugu follows the glossary (§8.1);
review status per string in docs/TELUGU_REVIEW.md."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Text:
    en: str
    te: str


# Customer-safe fallback for any failure the tool itself did not describe (docs/DESIGN.md §5, rule 4).
GENERIC_ERROR = Text(
    en="Sorry, I couldn't do that just now.",
    te="క్షమించండి, ఇప్పుడు అది చేయలేకపోయాను.",
)
GENERIC_NEXT_STEP = Text(
    en="Please ask me again in a moment.",
    te="దయచేసి కొద్దిసేపటి తర్వాత మళ్ళీ అడగండి.",
)
BAD_REQUEST_ERROR = Text(
    en="Sorry, I didn't catch all the details for that.",
    te="క్షమించండి, దానికి కావలసిన వివరాలు పూర్తిగా అందలేదు.",
)
BAD_REQUEST_NEXT_STEP = Text(
    en="Please say that again with a little more detail.",
    te="దయచేసి కొంచెం ఎక్కువ వివరాలతో మళ్ళీ చెప్పండి.",
)

# {app_en} / {app_te} are filled from config.APP_NAME / APP_NAME_TE (docs/DESIGN.md §11).
HELP_INTRO = Text(
    en="I'm {app_en}, your poultry farm helper.",
    te="నేను {app_te}, మీ కోళ్ల ఫారం సహాయకుడిని.",
)
HELP_TRY = Text(en="You can ask me:", te="మీరు నన్ను ఇలా అడగవచ్చు:")
HELP_NOTHING_YET = Text(
    en="My farm tools are still being set up, so right now I can only explain what I do.",
    te="నా ఫారం సేవలు ఇంకా సిద్ధమవుతున్నాయి, కాబట్టి ప్రస్తుతం నేను ఏమి చేస్తానో మాత్రమే చెప్పగలను.",
)

# Weather reminders (Step 50W-B). Forecast lines for the farmer's own outdoor-temperature rules. The Telugu below is a
# DRAFT awaiting native review (it is pending in docs/TELUGU_REVIEW.md). {source}: "Open-Meteo", or the existing
# "Simulated" label; {time}: when the forecast was fetched; the farmer's own note is inserted exactly as he wrote it.
WEATHER_LINE = Text(
    en=(
        "Forecast (hourly, outdoors at your farm's location, source: {source}; not real-time; fetched at {time}): "
        "{stat} is {value} degrees, {comparator} the number you set ({threshold})."
    ),
    te=(
        "అంచనా (గంటవారీ, మీ ఫారం ప్రాంతంలో బయట, మూలం: {source}; ప్రస్తుత కొలత కాదు; {time} కి తెచ్చినది): "
        "{stat} {value} డిగ్రీలు, మీరు పెట్టిన సంఖ్య ({threshold}) కంటే {comparator}."
    ),
)
WEATHER_LOWEST = Text(en="the lowest temperature", te="అత్యల్ప ఉష్ణోగ్రత")
WEATHER_HIGHEST = Text(en="the highest temperature", te="అత్యధిక ఉష్ణోగ్రత")
WEATHER_BELOW = Text(en="below", te="తక్కువ")
WEATHER_ABOVE = Text(en="above", te="ఎక్కువ")
WEATHER_NOTE = Text(en="Your note: {note}.", te="మీ గమనిక: {note}.")
WEATHER_UNAVAILABLE = Text(
    en="I couldn't get the weather forecast just now, so there is no weather reminder.",
    te="ఇప్పుడు వాతావరణ అంచనా దొరకలేదు, కాబట్టి వాతావరణ గుర్తు లేదు.",
)
