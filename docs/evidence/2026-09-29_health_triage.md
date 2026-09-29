# Evidence: Health Triage + vet handoff, step 1A (2026-09-29)

Demo mode (`MOCK_BEDROCK=true`: demo rules, no AI model, synthetic farm). Live Nova runs for this feature are
step 1B; the two live calls made so far were the spike in docs/AWS_SETUP.md §5.3.

## End to end: Simulator -> MCP server -> spoken answer
Real `python -m clucktalk.server` and `python -m clucktalk.simulator` processes, driven through the Simulator's own
`POST /api/turn` (the endpoint its web page uses), device "Echo Dot" (voice only), fresh state file.

| Farmer says | Tool (rule) | Round trip | Spoken answer |
|---|---|---|---|
| "Alexa, ask CluckTalk: shed 2 birds are coughing and not eating" | `start_health_check` | 218 ms | "While I check: House 2 needs your vet today. 26 birds died in the latest count, against about 4 a day before. Feed eaten is 18.4% below its recent level. I'm checking House 2 now. Ask me in a few seconds if the health check is ready." |
| "is the shed 2 health check ready" | `get_health_check` | 17 ms | "House 2 needs your vet today. 26 birds died in the latest count, against about 4 a day before. Feed eaten is 18.4% below its recent level. The signs fit a breathing problem (medium confidence) or a water or feed problem (medium confidence). First, call your vet today, remove dead birds quickly and bury them properly and separate the sick birds. This is guidance, not a diagnosis. Your vet decides any treatment. Shall I send a summary to your vet?" |
| "send the shed 2 health check to my vet" | `prepare_vet_handoff` (propose) | 22 ms | "I'll send your vet (demo contact) this summary by simulated SMS: House 2, Ross 308, day 23, 3,883 birds alive. 26 birds died in the latest count, against about 4 a day before. Feed eaten is 18.4% below its recent level. Signs reported: coughing and not eating. CluckTalk triage: needs a vet today (guidance, not a diagnosis). The farmer asks you to call back. Say yes to send it, or no to keep it." |
| "haan" | `prepare_vet_handoff` (answer yes) | 16 ms | "Sent to your vet (demo contact) as a simulated SMS." (after the wording fix; first run said "(simulated SMS in this demo)") |
| "house two swollen heads and blue combs, birds dying suddenly" | `start_health_check` | 15 ms | "House 2: these signs together can mean a serious bird disease that must be reported. 26 birds died in the latest count, against about 4 a day before. Feed eaten is 18.4% below its recent level. Now: stop all movement of birds, eggs, litter, vehicles and visitors in or out of the shed, separate the sick birds, do not cut open dead birds and report it today to your vet or the nearest government veterinary centre. This is guidance, not a diagnosis. Your vet decides any treatment. Shall I send a summary to your vet?" |

The red-flag answer came back ready in the same call, with no model call (the safety floor answers it).

## Harness
- `python tasks.py check`: PASSED (lint, format, 24 harness, unit, contract, AOSS, secret scan).
- `python tasks.py eval-fast`: 19/19 (was 10/10; +9 triage / vet-handoff cases, 0 regressions), including prompt
  injection, a model fixture that answers "routine" to everything (the floor holds), and a model fixture that
  always fails (the check says it couldn't finish and invents nothing).
- Mutation check (scratch script, byte-exact restore, `python -B`): 15 planted bugs in the floor, the reply
  validator, farmer-text sanitising, the per-check call limit, the daily cap, fail-loud, the red-flag fast answer,
  duplicate detection, the disclaimer, the vet summary and the shed check. First run 14/15; the survivor (the
  farmer's free text leaking into the vet SMS) exposed a missing test, which was added; 15/15 after that.

## Independent review (Rule 11) and fixes
A fresh reviewer read the code cold against docs/DESIGN.md §5-§7, §12, §18: 1 High, 3 Medium, 5 Low. All fixed,
each with a regression test written first (12 tests, all failing before the fix):
- High: a reply with a wrongly typed field (`"urgency": ["urgent"]`) raised `TypeError`, the job died, the check
  stayed "analyzing" forever and the live call was not ledgered. Fixed: type-checked validator; every acquired call
  ledgered before validation; any unexpected error marks the check failed; a check still "analyzing" after
  2 minutes (a lost job, e.g. a restart) reads as failed and never blocks a new check.
- Medium: a repeat within 10 minutes replayed the older check even after new deaths were logged (lower urgency).
  Fixed: a duplicate needs the same words and the same record-book facts.
- Medium: the vet SMS was rebuilt on "yes", so it could differ from the read-back (§5.1 rule 3). Fixed: the exact
  message is part of the proposal; a changed summary gets a fresh read-back. A summary sent before the check
  finishes says so ("still running; level from the signs and records so far").
- Medium: in the Simulator, "do a health check on shed 2, birds are coughing" went to "get result" and lost its
  signs. Fixed: signs are matched first.
- Low: disclaimer added to "still checking" (urgent floor) and "couldn't finish" answers; Telugu "call the vet"
  switched to the glossary's డాక్టర్‌కి ఫోన్ చేయండి; an unknown check_id says there is no check (not "that shed"
  as a shed name); boto3 client limited to 1 attempt, 5 s connect / 15 s read timeouts; unusable records are
  said ("this check is on the signs alone"); a stale docstring fixed.
After the fixes: `check` PASSED (24 harness, 364 unit, 170 contract), `eval-fast` 19/19, and the Simulator E2E
above was re-run with the same results plus the disclaimer in the first answer.
