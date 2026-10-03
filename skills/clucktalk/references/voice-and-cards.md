# Voice and cards

CluckTalk answers by voice first. A card, where there is one, shows the same answer. `docs/DESIGN.md` sections 5, 6, 14 and 15 are the source.

## What every result carries

- `text_en` and `text_te`: the same answer in English and in Telugu, with the same numbers. Numbers are written with Western digits in both languages (for example 1,23,456 in Indian grouping).
- `structuredContent`: the values the sentence was built from, validated against the tool's output schema.
- `_meta.ui.resourceUri` on the tool (in `tools/list`) when the tool has a card. Four cards serve five tools: `get_farm_status`, `plan_sale` and `get_daily_briefing` have one each, and `start_health_check` and `get_health_check` share the health card. Tools without a card declare none.
- `demo_data: true` while the data is the seeded demo farm.

The cards are: farm status, sell-day plan, health check (used by `start_health_check` and `get_health_check`) and daily briefing.

## Voice-only devices

An Echo Dot class device has no screen. For these:

- No card is requested or rendered. The spoken answer must be complete on its own.
- Never refer to a screen, a card or a tap ("see the card", "tap here").
- Offer at most 5 options at a time. `get_daily_briefing` reads the top 3 and offers "more" for the rest (5 items at most).
- Read a change back in full, then wait for an explicit yes or no (haan, avunu / nahi, vaddu).

## Devices with a screen (an Echo Show class device)

- Speak the answer and show the card. The card is an MCP App served as a `ui://` resource, one self-contained HTML document with no outside requests.
- Status is an icon and a word, never colour alone. Key numbers are large; the least important line comes last.
- English and Telugu appear side by side on the card.
- A tap on a card calls the same tool voice would call (for example a tap on a shed tile calls `get_farm_status` for that shed) and gives the same answer. A tap never stands in for a spoken yes.
- If a card cannot render, show the labelled text answer instead; never leave a blank card. A previous card must be removed as soon as a new question is asked, so no stale card stays on screen.
- A turn slower than 1 second should say "Still working" rather than stay silent.

## Spoken numbers equal card numbers

This is the cross-modal rule. Every number on a card is a value from the tool's `structuredContent`, formatted the way the spoken sentence formats it. The card does no arithmetic on data, and a finding sentence on a card is the tool's own sentence. In a host that speaks the tool's own text (the local Simulator) that is the exact sentence the voice says; on Alexa+ the assistant words its own answer, so the wording may differ and only the numbers are guaranteed to match. The same holds for the follow-up: the card shows the follow-up sentence verbatim, so the number of days since the health check on the card is the number in the tool's sentence. Do the same in anything you add: never round, convert or recompute a number the result already gives.

English and Telugu speak the same numbers. The farmer's language decides which sentence you speak; do not mix the two in one sentence.

## Markers a card or result can carry

- A "Demo data" badge on every card in demo mode.
- "Simulated" on market prices, sensors, the supplier message and the vet message.
- A "Demo clock: +N days" badge, only while the operator has turned the demo clock on for a recording. It comes from `_meta`, not `structuredContent`, and it never appears when the clock is off. Do not describe the shifted date as real. Its honest scope: it shifts follow-up and briefing dates only; flock ages, record-book entries and the sale plan do not move, so never present it as time passing for the flock.

## Errors and waiting

- An error is one customer-safe sentence plus one next step. Cards show it in both languages; voice speaks the English `content` sentence or the Telugu one.
- A health check runs in the background: the first result says it is still checking, and the farmer or agent asks `get_health_check` a few seconds later. Signs that need action at once are answered immediately from code.
- Every tool answers from stored state, with no model call inside a tool, so a tool returns quickly. If the server is down, say that plainly.
