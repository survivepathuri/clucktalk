---
name: clucktalk
description: "How an AI agent should operate the CluckTalk MCP server, a voice farm manager for Indian poultry farmers (Telugu subtitle: kodi mitra). Use when a farmer asks, by voice or text, how a shed is doing, about a daily briefing, feed stock, the best day to sell broilers, a record-book entry, signs of illness in a shed, sending a health check to the vet, or how a shed is now after a check, or when you must call, test or review CluckTalk tools. Covers tool routing, the propose, read-back, yes protocol, the safety rules, voice-only versus card behaviour, and the rule that spoken numbers equal card numbers."
license: MIT
---

# Operating CluckTalk

CluckTalk is a self-hosted MCP server (protocol 2025-11-25, Streamable HTTP) for Indian poultry farmers, with English and Telugu answers and four optional cards. This skill teaches an agent how to operate CluckTalk. It does not claim that Alexa+ runs it: no Alexa+ device has loaded it, and the local Simulator in the repo is what plays the host role today.

Everything here comes from the server's code and `docs/DESIGN.md`. If this skill and the server disagree, the server wins; say so and fix the skill.

The farm is always seeded, fictional demo data (live AI mode also runs on it). Results carry `demo_data` and the cards show a "Demo data" badge. Market prices, sensors, supplier messages and the vet message are always labelled "Simulated". Never present them as real.

## Read these when you need the detail

- `references/tool-routing.md`: all 14 tools, the farmer's words for each (shed / kotam / house; haan / avunu / nahi / vaddu), and example phrases that the Simulator routes as stated.
- `references/safety-rules.md`: the rules that no answer may break.
- `references/voice-and-cards.md`: voice-only versus card behaviour and the cross-modal rule.

## The 14 tools in one line each

| Tool | Use it when the farmer |
|---|---|
| `get_farm_status` | asks how a shed or the whole farm is doing |
| `plan_sale` | asks when to sell a broiler shed |
| `get_daily_briefing` | asks for today's briefing, or says "more" after it |
| `start_health_check` | describes signs of illness in a shed |
| `get_health_check` | asks whether a health check is ready |
| `prepare_vet_handoff` | wants the vet to get a health check summary |
| `report_health_follow_up` | says how a shed is now compared with its last health check |
| `plan_feed` | asks about feed stock, reorder or the feed phase |
| `get_farm_profile` | asks whether the farm is set up as contract or independent |
| `set_farm_mode` | wants to change that |
| `set_contract_terms` | wants to save the numbers of their own growing contract |
| `get_record_book` | asks which sheds have a record for today |
| `log_daily_record` | reports deaths, feed given, a weight reading or a treatment given |
| `get_help` | asks what CluckTalk can do |

One tool is one intent. Pick the tool from what the farmer wants, pass the farmer's own shed words through unchanged (the server resolves "shed 2", "kotam do", "house two", "do number shed"), and never guess a shed: an unknown or ambiguous shed returns the real labels, so ask the farmer which one.

## Changes: propose, read back, yes

Five tools change something and use one pattern and no other: `set_farm_mode`, `set_contract_terms`, `log_daily_record`, `prepare_vet_handoff` and `report_health_follow_up`. (`start_health_check` also stores a check, but it takes no `proposal_id` and no `answer`.)

1. **Propose.** Call the tool with the farmer's request and no `proposal_id`. Nothing changes. The result has `status: "needs_confirmation"`, a `proposal_id`, and a read-back in full.
2. **Read it back** to the farmer, word for word, then stop and wait.
3. **Answer.** Only an explicit whole-sentence yes (yes, haan, avunu) or no (no, nahi, vaddu) counts. Call the same tool again with the same arguments plus `proposal_id` and `answer: "yes"` or `"no"`. In the Simulator host any other utterance drops the pending read-back; do the same, and make a new proposal if they still want the change.
4. The change applies only when the arguments equal what was read back and the proposal is unexpired (10 minutes). A correction is a new proposal. Repeating a confirmed `proposal_id` returns the same outcome and never applies twice.

A card tap never stands in for a spoken yes. Never invent an answer for the farmer.

## Safety, in short (full list in `references/safety-rules.md`)

- Never name a medicine or give a dose, and never ask for one. `log_daily_record` keeps a treatment name only, and `report_health_follow_up` has no free-text argument at all.
- Health checks are guidance, not a diagnosis. A suspected reportable disease gets no diagnosis: the result says to report it and offers the vet handoff.
- An answer to a follow-up never lowers a health check's urgency. "Same", "worse" and "not sure" all end with "To be safe, contact your vet or doctor." A death spike in the record book counts as worse whatever the farmer says.
- Never reassure, never give rearing advice, never promise a reminder or any proactive contact. CluckTalk only answers when the farmer asks; the next briefing asks about a shed only when the farmer next opens it.
- Never say a number the result does not contain. Never report an unknown farm level as ok.

## Voice and cards, in short (full list in `references/voice-and-cards.md`)

- Every result has `text_en`, `text_te` and `structuredContent`. Speak the sentence in the farmer's language; the card shows the same sentence and the same numbers.
- Voice-only devices (an Echo Dot class device) get no card. The spoken answer must be complete on its own and must never refer to a screen. Offer at most 5 options.
- Where a card exists, the tool declares it in `_meta.ui.resourceUri`. A tap on a card calls the same tool as voice and gives the same answer.

## Errors

A failed call has `isError: true`, one customer-safe sentence in `content` and one next step. Speak that, and nothing else. Never speak codes, tool names, JSON or IDs. If the server is down, say so plainly and do not make anything up.

## When testing CluckTalk

Run it with `python tasks.py serve` (MCP server only) or `python tasks.py run` (with the Simulator), then `python tasks.py check` and `python tasks.py eval-fast`. The mock host's routing rules are in `src/clucktalk/simulator/intents.py`; the examples in `references/tool-routing.md` are tested against them.
