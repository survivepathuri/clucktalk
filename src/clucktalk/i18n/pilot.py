"""The words on the pilot page (Step 51 part C): a Telugu-first phone page for the farmer's own pilot. The Telugu
below is a DRAFT awaiting native review (every line is pending in docs/TELUGU_REVIEW.md); none is marked reviewed.
Answers themselves (status, briefing, read-backs, errors) come from the tools' own ``text_te``; these are only the
page's own words. ``PILOT_UI`` is what the page loads, so the page holds no wording of its own."""

from __future__ import annotations

from clucktalk.i18n import GENERIC_ERROR, GENERIC_NEXT_STEP, PILOT_BADGE, Text

PILOT_NOTICE = Text(
    en="Your keyboard's voice typing sends what you say to its own speech service. CluckTalk never hears your voice.",
    te="మీ కీబోర్డ్ వాయిస్ టైపింగ్ మీరు చెప్పింది దాని స్పీచ్ సేవకు పంపుతుంది. కోడి మిత్రకు మీ గొంతు వినిపించదు.",
)
NOT_UNDERSTOOD = Text(
    en="I did not understand. Tap one of these.",
    te="నాకు అర్థం కాలేదు. వీటిలో ఒకటి నొక్కండి.",
)
NOTHING_PENDING = Text(
    en="There is nothing waiting for a yes or no. Tap one of these.",
    te="అవును లేదా వద్దు కోసం ఏమీ వేచి లేదు. వీటిలో ఒకటి నొక్కండి.",
)
YES_BUTTON = Text(en="Yes", te="అవును")
NO_BUTTON = Text(en="No", te="వద్దు")
READBACK_HEAD = Text(en="Is this right?", te="ఇది సరైనదేనా?")
HOST_NOT_STARTED = Text(en="OK, I did not start it.", te="సరే, మొదలుపెట్టలేదు.")
SHED_LABEL = Text(en="shed {number}", te="షెడ్ {number}")
HEALTH_READBACK = Text(
    en="Start a health check for {shed} with these signs: {signs}?",
    te="{shed} కి ఈ లక్షణాలతో ఆరోగ్య పరీక్ష మొదలుపెట్టమంటారా: {signs}?",
)

CHIP_DEATHS = Text(en="Log deaths", te="మరణాలు నమోదు")
CHIP_NO_DEATHS = Text(en="No deaths today", te="ఈరోజు మరణాలు లేవు")
CHIP_STATUS = Text(en="How is the farm?", te="ఫారం ఎలా ఉంది?")
CHIP_BRIEFING = Text(en="Today's briefing", te="ఈరోజు బ్రీఫింగ్")
CHIP_HEALTH = Text(en="Health check", te="ఆరోగ్య పరీక్ష")
CHIP_SALE = Text(en="When to sell?", te="ఎప్పుడు అమ్మాలి?")
CHIP_FOLLOW_UP = Text(en="Birds after the check", te="పరీక్ష తర్వాత కోళ్లు")
CHIP_HELP = Text(en="Help", te="సహాయం")
OUTCOME_BETTER = Text(en="Better", te="బాగుంది")
OUTCOME_SAME = Text(en="The same", te="అలాగే ఉంది")
OUTCOME_WORSE = Text(en="Worse", te="అధ్వాన్నంగా ఉంది")

CHIPS = {
    "deaths": CHIP_DEATHS,
    "no_deaths": CHIP_NO_DEATHS,
    "status": CHIP_STATUS,
    "briefing": CHIP_BRIEFING,
    "health": CHIP_HEALTH,
    "sale": CHIP_SALE,
    "follow_up": CHIP_FOLLOW_UP,
    "help": CHIP_HELP,
}
OUTCOMES = {"better": OUTCOME_BETTER, "same": OUTCOME_SAME, "worse": OUTCOME_WORSE}

PILOT_UI = {
    "badge": PILOT_BADGE,
    "notice": PILOT_NOTICE,
    "not_understood": NOT_UNDERSTOOD,
    "nothing_pending": NOTHING_PENDING,
    "yes": YES_BUTTON,
    "no": NO_BUTTON,
    "readback": READBACK_HEAD,
    "not_started": HOST_NOT_STARTED,
    "error": GENERIC_ERROR,
    "error_next": GENERIC_NEXT_STEP,
}
