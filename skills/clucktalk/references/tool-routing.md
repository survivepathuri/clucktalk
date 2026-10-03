# Tool routing

Which tool for which words. One tool is one intent. The farmer's shed words are passed through unchanged and the server resolves them, so never rewrite "kotam do" into an ID yourself.

## The tools

| Tool | Changes something? | Has a card? | Needs | Use it when the farmer |
|---|---|---|---|---|
| `get_farm_status` | no | yes | `house` optional; omit for the whole farm | asks how a shed or the farm is doing right now: deaths, feed intake, weight against the breed target, feed stock running low, and any open health check or follow-up for that shed. Not for today's priorities (use `get_daily_briefing`) and not for new signs (use `start_health_check`) |
| `plan_sale` | no | yes | `house` optional, `live_price_per_kg` if the farmer states today's rate | asks when to sell a broiler shed, whether to wait, the best day or the break-even day. Not for layer flocks |
| `get_daily_briefing` | no | yes | `more: true` to hear the rest | asks for today's briefing, the daily update, or what to do first today. Covers the whole farm and takes no shed; not for one shed's numbers (use `get_farm_status`). Reads the top 3 of at most 5 items; health items come first |
| `start_health_check` | yes (stores a check) | yes | `house`, `signs` (mapped onto the allowed values), the farmer's own words in `symptoms` | describes signs of illness in a shed |
| `get_health_check` | no | yes | `house` or `check_id` | asks whether a health check is ready or what it found |
| `prepare_vet_handoff` | yes (read-back, then yes) | no | `house`, optionally `check_id` | wants the vet to get a summary of a health check. In the demo the message is a simulated SMS |
| `report_health_follow_up` | yes (read-back, then yes) | no | `house`, `outcome`: better, same, worse or not_sure | says how a shed that had a health check is doing now compared with then |
| `plan_feed` | no | no | `house` optional, `horizon_days` optional | asks about feed (dana): how much is needed, how long the stock lasts, whether to reorder. It plans only and never places an order |
| `get_farm_profile` | no | no | nothing | asks whether the farm is contract or independent |
| `set_farm_mode` | yes (read-back, then yes) | no | `mode`: contract or independent | wants to change that |
| `set_contract_terms` | yes (read-back, then yes) | no | four numbers from the farmer's own agreement | wants to save their growing-contract terms |
| `get_record_book` | no | no | nothing | asks which sheds have a record logged for today |
| `log_daily_record` | yes (read-back, then yes) | no | `house`, and whichever of deaths, feed bags, average weight with the number of birds weighed, or treatments the farmer mentioned | reports what happened in a shed |
| `get_help` | no | no | nothing | asks what CluckTalk can do |

Rules that hold for every tool:

- A shed is named as the farmer says it. Synonyms: shed, house, kotam (also kottam, kotham), coop; numbers as digits, English words, ordinals (second shed) or Hinglish words (ek, do, teen, char, paanch).
- Several constraints in one sentence go in one call (one-shot extraction). A correction changes one field.
- For `set_contract_terms`, never suggest numbers from any company. Ask the farmer to read all four from their own paperwork.
- If the farmer describes new signs of illness while talking about a follow-up, call `start_health_check`, not `report_health_follow_up`.
- Signs of illness win over everything else in the same sentence: a sick-bird report must never turn into a silent log entry, a result lookup or a vet message without its health check.
- No rule matches: say what CluckTalk can do and make no call. Do not guess a tool.

## Example phrases

Each row below is run through the Simulator's intent rules by a test (`tests/unit/test_skill.py`), so the tool and the arguments shown are what the mock host really sends. The real Alexa+ assistant has not been tested on these phrases.

### Farm status, with the three words for a shed

| Phrase | Tool | Arguments |
|---|---|---|
| "how is shed 2" | `get_farm_status` | `house=shed 2` |
| "how is kotam do" | `get_farm_status` | `house=kotam do` |
| "how is house three" | `get_farm_status` | `house=house three` |
| "how is the farm" | `get_farm_status` | |

### Briefing, record book, help

| Phrase | Tool | Arguments |
|---|---|---|
| "today's briefing" | `get_daily_briefing` | |
| "daily update" | `get_daily_briefing` | |
| "more" | `get_daily_briefing` | `more=true` |
| "what's logged today" | `get_record_book` | |
| "what can you do" | `get_help` | |

### Farm type

| Phrase | Tool | Arguments |
|---|---|---|
| "what kind of farm is this" | `get_farm_profile` | |
| "switch to contract farming" | `set_farm_mode` | `mode=contract` |
| "change to independent farming" | `set_farm_mode` | `mode=independent` |

### Feed and sale

| Phrase | Tool | Arguments |
|---|---|---|
| "how much feed does shed 2 need" | `plan_feed` | `house=shed 2` |
| "kotam teen dana stock" | `plan_feed` | `house=kotam teen` |
| "when should I sell shed 2" | `plan_sale` | `house=shed 2` |
| "shed 1 kab bechun" | `plan_sale` | `house=shed 1` |
| "shed 1 rate is 95" | `plan_sale` | `live_price_per_kg=95.0` |

### Record book entries (read-back, then yes)

| Phrase | Tool | Arguments |
|---|---|---|
| "shed 2 5 birds died" | `log_daily_record` | `house=shed 2`, `deaths=5` |
| "2 bags of feed for shed 2" | `log_daily_record` | `house=shed 2` |
| "kotam do mar gaye 3" | `log_daily_record` | `house=kotam do` |

### Health: signs, result, vet

| Phrase | Tool | Arguments |
|---|---|---|
| "shed 2 birds are coughing" | `start_health_check` | `house=shed 2` |
| "kotam one sneezing and not eating" | `start_health_check` | `house=kotam one` |
| "shed 3 health check ready" | `get_health_check` | `house=shed 3` |
| "send the shed 2 summary to my vet" | `prepare_vet_handoff` | `house=shed 2` |

### How a shed is now (follow-up; read-back, then yes)

| Phrase | Tool | Arguments |
|---|---|---|
| "shed 2 is better now" | `report_health_follow_up` | `house=shed 2`, `outcome=better` |
| "kotam do is better now" | `report_health_follow_up` | `house=kotam do`, `outcome=better` |
| "shed 3 theek ho gaya" | `report_health_follow_up` | `house=shed 3`, `outcome=better` |
| "shed 2 is the same" | `report_health_follow_up` | `outcome=same` |
| "shed 2 waisa hi hai" | `report_health_follow_up` | `outcome=same` |
| "shed 2 is worse now" | `report_health_follow_up` | `outcome=worse` |
| "house 1 aur kharab ho gaya" | `report_health_follow_up` | `house=house 1`, `outcome=worse` |
| "shed 1 not sure" | `report_health_follow_up` | `outcome=not_sure` |
| "shed one pata nahi" | `report_health_follow_up` | `house=shed one`, `outcome=not_sure` |

When two outcomes are said in one sentence, the more worrying one is sent. "Not better" counts as same, and "not worse" counts as not sure. If no shed is named, ask which one; never guess.

### The answer to a read-back

These words only answer a pending read-back. On their own they are no tool call, and a yes with nothing pending makes no call.

| Word | Meaning | Arguments |
|---|---|---|
| "yes" | answer: yes | |
| "haan" | answer: yes | |
| "avunu" | answer: yes | |
| "confirm" | answer: yes | |
| "no" | answer: no | |
| "nahi" | answer: no | |
| "vaddu" | answer: no | |
| "cancel" | answer: no | |

## Not covered by the mock host's rules

`set_contract_terms` has no phrase rule in the Simulator, because it needs four numbers that the farmer reads out of their own agreement. A real host routes it from the tool's own description. It uses the same read-back and yes pattern, and it refuses any argument it does not list.
