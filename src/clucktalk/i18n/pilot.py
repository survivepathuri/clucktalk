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
# The bare paper rate: RATE_ASK is the start of the sell question's ask line, RATE_PHRASE the words the server's typed
# matcher already accepts before the number. Both are pieces of sentences the server already says (tools/sale.py).
RATE_ASK = Text(en="Tell me today's paper rate", te="ఈరోజు పేపర్ రేటు చెప్పండి")
RATE_PHRASE = Text(en="today's paper rate", te="ఈరోజు పేపర్ రేటు")

# The Questions button (farmer_schedule in the farm file). Every answer is built only from what the farmer
# himself told us and starts with AS_TOLD: it is his own routine read back, never advice and never a checked fact.
# All Telugu below is a DRAFT in simple village Telugu, pending native review (docs/TELUGU_REVIEW.md).
# {shed} is SHED_LABEL; days are his own days.
QUESTIONS_BUTTON = Text(en="Questions", te="ప్రశ్నలు")
AS_TOLD = Text(en="As you told us:", te="మీరు చెప్పినట్లు:")
QUESTION_LABELS = {
    1: Text(en="What day is it today?", te="ఈరోజు ఎన్నో రోజు?"),
    2: Text(en="When is the next vaccination?", te="తదుపరి టీకా ఎప్పుడు?"),
    3: Text(en="Is there a vaccination today?", te="ఈరోజు టీకా ఉందా?"),
    4: Text(en="From when should I weigh the birds?", te="ఎప్పటి నుంచి బరువు చూడాలి?"),
    5: Text(en="When should I spray water?", te="నీళ్లు ఎప్పుడు చల్లాలి?"),
    6: Text(en="For how many days the heat lights?", te="వేడి లైట్లు ఎన్ని రోజులు?"),
    7: Text(en="When does the doctor come?", te="డాక్టర్ ఎప్పుడు వస్తారు?"),
    8: Text(en="How much feed in all for one bird?", te="ఒక కోడికి మొత్తం దాణా ఎంత?"),
    9: Text(en="What weight on day 45?", te="45వ రోజు బరువు ఎంత ఉండాలి?"),
    10: Text(en="When is day 45?", te="45వ రోజు ఎప్పుడు?"),
}
ANSWER_DAY = Text(en="{shed}: day {day}.", te="{shed}: {day}వ రోజు.")
ANSWER_NEXT_VACCINE = Text(
    en="{shed}: next vaccination on day {day}, in {left} days.",
    te="{shed}: తదుపరి టీకా {day}వ రోజున, {left} రోజుల్లో.",
)
ANSWER_VACCINE_TODAY_NEXT = Text(
    en="{shed}: next vaccination is today, day {day}.",
    te="{shed}: తదుపరి టీకా ఈరోజే, {day}వ రోజు.",
)
ANSWER_VACCINES_OVER = Text(
    en="{shed}: the vaccination days you told us are all over.",
    te="{shed}: మీరు చెప్పిన టీకా రోజులన్నీ అయిపోయాయి.",
)
ANSWER_VACCINE_YES = Text(en="{shed}: yes, vaccination today, day {day}.", te="{shed}: అవును, ఈరోజు టీకా ఉంది, {day}వ రోజు.")
ANSWER_VACCINE_NO = Text(en="{shed}: no vaccination today, day {day}.", te="{shed}: లేదు, ఈరోజు టీకా లేదు, {day}వ రోజు.")
ANSWER_WEIGH_FROM = Text(en="Weigh the birds from day {day}.", te="{day}వ రోజు నుంచి కోళ్లను తూకం వేయండి.")
ANSWER_WEIGH_OK = Text(en="On day 40, above {kg} kg is good.", te="40వ రోజున {kg} కిలోల కంటే ఎక్కువ ఉంటే బాగుంది.")
ANSWER_SPRAY = Text(
    en="Spray water when it is hotter than {degrees} degrees.",
    te="వేడి {degrees} డిగ్రీల కంటే ఎక్కువ ఉన్నప్పుడు నీళ్లు చల్లండి.",
)
ANSWER_LIGHTS_ON = Text(
    en="{shed}: heat lights for the first {days} days; now day {day}, keep them on.",
    te="{shed}: మొదటి {days} రోజులు వేడి లైట్లు; ఇప్పుడు {day}వ రోజు, ఇంకా ఉంచాలి.",
)
ANSWER_LIGHTS_OVER = Text(
    en="{shed}: heat lights were for the first {days} days; now day {day}, those days are over.",
    te="{shed}: మొదటి {days} రోజులు వేడి లైట్లు; ఇప్పుడు {day}వ రోజు, ఆ రోజులు అయిపోయాయి.",
)
ANSWER_VET = Text(en="The doctor comes every {days} days.", te="డాక్టర్ {days} రోజులకు ఒకసారి వస్తారు.")
ANSWER_VET_DAILY = Text(en="The doctor comes every day.", te="డాక్టర్ రోజూ వస్తారు.")
ANSWER_FEED = Text(
    en="One bird eats about {kg} kg of feed in all by day 45.",
    te="ఒక కోడికి 45వ రోజు వరకు మొత్తం సుమారు {kg} కిలోల దాణా.",
)
ANSWER_WEIGHT = Text(en="On day 45 the weight should be about {kg} kg.", te="45వ రోజున బరువు సుమారు {kg} కిలోలు ఉండాలి.")
ANSWER_DAY_45 = Text(en="{shed}: day 45 is on {date}.", te="{shed}: 45వ రోజు {date} నాడు.")
NO_FLOCK = Text(en="No shed has birds now.", te="ఇప్పుడు ఏ షెడ్ లోనూ కోళ్లు లేవు.")

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
    "rate_ask": RATE_ASK,
    "rate_phrase": RATE_PHRASE,
    "questions": QUESTIONS_BUTTON,
}
