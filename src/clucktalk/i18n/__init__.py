"""Fixed bilingual strings (docs/DESIGN.md §8). Every Telugu string is pending native-speaker review."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Text:
    en: str
    te: str


# Telugu below was drafted without a native speaker. Keep this flag True until a reviewer signs off,
# and list the reviewer + date in docs/SOURCES.md when it flips.
TE_REVIEWED = False

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
