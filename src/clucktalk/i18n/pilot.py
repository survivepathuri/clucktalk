"""The words on the pilot page (Step 51 part C): a Telugu-first phone page for the farmer's own pilot. The Telugu
below is a DRAFT awaiting native review (every line is pending in docs/TELUGU_REVIEW.md); none is marked reviewed.
Answers themselves (status, briefing, read-backs, errors) come from the tools' own ``text_te``; these are only the
page's own words. ``PILOT_UI`` is what the page loads, so the page holds no wording of its own."""

from __future__ import annotations

import hashlib

from clucktalk.i18n import GENERIC_ERROR, GENERIC_NEXT_STEP, PILOT_BADGE, Text
from clucktalk.server.cards import FARM_STATUS_LABELS

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

# Step 52 part C: the one-screen notice shown on first open. The Telugu is taken from the drafts written for the
# farmer's notice (private, untracked); all of it is a DRAFT awaiting native review (pending in docs/TELUGU_REVIEW.md).
NOTICE_TITLE = Text(en="Before you start", te="మొదలుపెట్టే ముందు")
NOTICE_ACK = Text(en="I understand", te="అర్థమైంది")
NOTICE_TEST = Text(en="This is a test. It is not a veterinary service.", te="ఇది ఒక పరీక్ష మాత్రమే. ఇది పశువైద్య సేవ కాదు.")
NOTICE_VET = Text(
    en="For a sick bird, call your vet.",
    te="కోడి అనారోగ్యంగా ఉంటే మీ డాక్టర్‌కి ఫోన్ చేయండి.",
)
NOTICE_ALERT = Text(
    en="An alert is a reminder to go and look at the birds. It is not a diagnosis.",
    te="హెచ్చరిక అంటే కోళ్లను వెళ్లి చూడమని గుర్తు చేయడం మాత్రమే. అది రోగ నిర్ధారణ కాదు.",
)
NOTICE_TARGETS = Text(
    en="The weight and total-deaths targets are general numbers. They may not fit your birds.",
    te="బరువు, మొత్తం మరణాల లక్ష్యాలు సాధారణ సంఖ్యలు. అవి మీ కోళ్లకు సరిపోకపోవచ్చు.",
)
NOTICE_STORED = Text(
    en=(
        "We keep your houses, the deaths and feed you log, and your yes and no answers with their dates. "
        "We do not keep your voice, your name or where you live. I (the builder) can read all of it on my server. "
        "Nobody else can unless I give them access."
    ),
    te=(
        "మేము మీ షెడ్లు, మీరు నమోదు చేసే మరణాలు, మేత వివరాలు, మరియు మీ అవును/వద్దు సమాధానాలను తేదీలతో ఉంచుతాము. "
        "మీ గొంతు, మీ పేరు, మీరు ఉండే చోటు మేము ఉంచము. ఇవన్నీ నేను (తయారుచేసినవాడిని) నా సర్వర్‌లో చూడగలను. "
        "నేను అనుమతి ఇస్తే తప్ప ఇంకెవరూ చూడలేరు."
    ),
)
NOTICE_DELETE = Text(
    en="You can ask me at any time to delete it. I will delete everything and tell you when it is done.",
    te="మీరు ఎప్పుడైనా తొలగించమని అడగవచ్చు. అంతా తొలగించి, పూర్తయినప్పుడు మీకు చెబుతాను.",
)
OPEN_LINK = Text(en="Open your original link.", te="మీ అసలు లింక్‌ను తెరవండి.")
# The seven things he is told once, on one screen, before anything works (the voice-typing line is PILOT_NOTICE above).
NOTICE_ITEMS = (NOTICE_TEST, NOTICE_VET, NOTICE_ALERT, NOTICE_TARGETS, PILOT_NOTICE, NOTICE_STORED, NOTICE_DELETE)


def notice_version() -> str:
    """Changes whenever the wording of the notice does, so he is asked to acknowledge the new wording."""
    text = "".join(f"{t.en}{t.te}" for t in NOTICE_ITEMS)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


BUTTON_ADD = Text(en="Add", te="కలపండి")
BUTTON_REPLACE = Text(en="Replace", te="మార్చండి")

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

# Commit A (the page's look): new words, all DRAFTS awaiting native review (pending in docs/TELUGU_REVIEW.md). The ALERT
# word and the deaths label are the status card's own (FARM_STATUS_LABELS), not new. The vet line is the phrase of the
# farmer's-own-limit sentence the server already says, shown big only when that rule fired. SAY_SUFFIX is how every
# yes-or-no read-back ends on the server; the page swaps it for TAP_SUFFIX because the farmer taps buttons here.
ALERT_WORD = FARM_STATUS_LABELS["level_alert"]
DEATHS_TODAY = FARM_STATUS_LABELS["deaths_today"]
VET_TODAY = Text(en="Take the birds to the vet today", te="ఈరోజే కోళ్లను డాక్టర్ దగ్గరికి తీసుకెళ్లండి")
WARN_TAG = Text(en="Note", te="గమనిక")
INPUT_PLACEHOLDER = Text(en="Write here", te="ఇక్కడ రాయండి")
SEND_BUTTON = Text(en="Send", te="పంపండి")
SAY_SUFFIX = Text(en="(the ending that asks you to say yes or no)", te="అని చెప్పండి.")
TAP_SUFFIX = Text(en="(the ending that asks you to tap yes or no)", te="నొక్కండి.")

PILOT_UI = {
    "badge": PILOT_BADGE,
    "notice": PILOT_NOTICE,
    "not_understood": NOT_UNDERSTOOD,
    "nothing_pending": NOTHING_PENDING,
    "yes": YES_BUTTON,
    "no": NO_BUTTON,
    "readback": READBACK_HEAD,
    "not_started": HOST_NOT_STARTED,
    "notice_title": NOTICE_TITLE,
    "ack": NOTICE_ACK,
    "add": BUTTON_ADD,
    "replace": BUTTON_REPLACE,
    "error": GENERIC_ERROR,
    "error_next": GENERIC_NEXT_STEP,
    "alert": ALERT_WORD,
    "deaths_today": DEATHS_TODAY,
    "vet_today": VET_TODAY,
    "warn_tag": WARN_TAG,
    "placeholder": INPUT_PLACEHOLDER,
    "send": SEND_BUTTON,
    "say_suffix": SAY_SUFFIX,
    "tap_suffix": TAP_SUFFIX,
}
