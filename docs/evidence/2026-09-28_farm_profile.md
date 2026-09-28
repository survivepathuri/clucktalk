# Evidence: state store, one confirmation pattern, farm profile (2026-09-28)

Windows 11 Pro, Python 3.13.15 (SQLite 3.50.4, stdlib `sqlite3`), headless Google Chrome 153.0.8010.53, demo data
(`MOCK_BEDROCK=true`). Design: docs/DESIGN.md §5.1 (confirmation pattern) and §13.1 (farm profile).

## 1. Harness

`python tasks.py check` → PASSED: lint, format, **24 harness, 232 unit, 103 contract**, AOSS, secret scan
(before this change: 21 / 147 / 79; final numbers, after the review fixes in §6).

New tests: `tests/unit/test_proposals.py` (every §5.1 rule as a table), `test_store.py` (round trips, restart,
rollback, loud failure on an incompatible file, no dose field on treatments), `test_confirm_flow.py` (apply once,
expiry, supersede, cancel, foreign IDs, failing change rolls back), `tests/contract/test_profile_tools.py` (over real
HTTP: output schemas, two-call pattern, contract-mode answers, 5 concurrent identical "yes" → applied once),
Simulator host rules and yes/no turns, `tests/harness/test_reset_demo.py`.

Existing tests changed: two unit-test fakes gained `profile()` (the source interface grew); the help test now expects
the new `set_farm_mode` capability. No assertion was loosened.

## 2. Mutation check (scratch script, byte-exact restore, `-B`)

17 of 17 planted bugs were caught (final run, after the review fixes): yes applied with different arguments; expiry
off by one; a cancelled proposal revived by yes; a repeated yes applied again; no supersede; `atomic()` committing
instead of rolling back; contract mode still pricing feed; the already-set check skipped; a partial "yes" sent as an
answer; a read-back kept after the farmer moves on; reset-demo deleting any file; and one per review fix (already-set
not withdrawing the older read-back, failed COMMIT not rolled back, a late "no" answered as "Done", a negated
sentence starting a switch, a relative state path not anchored to the repo, a contract plan flagging a simulated
price). One mutant in the first round was equivalent (a `tasks.py` suffix check that config now makes unreachable);
the dead check was removed and the mutant moved to the config check.

## 3. End to end in the Simulator (real MCP calls, typed turns, Echo Show 1024×600)

| # | Farmer says | Tool call the host made | CluckTalk says |
|---|---|---|---|
| 1 | What kind of farm is this? | `get_farm_profile {}` | Your farm is set up as an independent farm: you buy your own feed, so feed plans include a simulated price. … |
| 2 | Switch my farm to contract farming | `set_farm_mode {"mode":"contract"}` | Switch your farm to contract farming? … Say yes to confirm, or no to keep it as it is. ([01](2026-09-28_farm_profile/01_switch-to-contract_read-back.png)) |
| 3 | haan | `set_farm_mode {"mode":"contract","proposal_id":"prop_…","answer":"yes"}` | Done. Your farm is now set up as a contract farm. ([02](2026-09-28_farm_profile/02_haan_applied.png)) |
| 4 | Feed plan for shed two | `plan_feed {"house":"shed two"}` | … Ask your supervisor for 51 bags of 50 kg now. … (no price; [03](2026-09-28_farm_profile/03_contract_feed-plan_supervisor-no-price.png)) |
| 5 | How is shed two doing? | `get_farm_status {"house":"shed two"}` | … Ask me for a feed plan to hear how much feed to ask your supervisor for. Card: cross-modal ✓ (11 spoken numbers on the card, 25 card numbers in the result) ([04](2026-09-28_farm_profile/04_contract_status-card_cross-modal.png)) |
| 6 | yes | none (nothing pending) | Host: There's nothing waiting for a yes or no right now. ([05](2026-09-28_farm_profile/05_stray-yes_no-tool-call.png)) |

Restart (`python tasks.py run` stopped and started again, same `.local/clucktalk.sqlite3`):

| # | Farmer says | Result |
|---|---|---|
| 1 | What kind of farm is this? | still **contract** ([06](2026-09-28_farm_profile/06_after-restart_still-contract.png)) |
| 2–3 | change to independent farming → nahi | `answer: "no"` → Okay, nothing changed. Your farm stays a contract farm. ([07](2026-09-28_farm_profile/07_nahi_nothing-changed.png)) |

`python tasks.py reset-demo` while the demo runs → exit 1, "… is in use. Stop the running demo (Ctrl+C), then run
reset-demo again." After stopping → "deleted …\.local\clucktalk.sqlite3". Next start: independent farm, and the feed
plan is priced again: "Order 51 bags of 50 kg now: about ₹98,175 before GST and delivery, at the simulated price of
₹38.50 a kilo." ([08](2026-09-28_farm_profile/08_after-reset-demo_independent-priced.png))

## 4. Latency (`scripts/latency_report.py -n 200`, loopback HTTP, in-memory store)

| Call | p50 ms | p95 ms | max ms |
|---|---|---|---|
| get_farm_profile | 2.1 | 2.7 | 3.2 |
| set_farm_mode (propose: 2 writes + read-back) | 2.4 | 3.7 | 4.5 |
| get_farm_status (whole farm) | 5.6 | 6.9 | 8.1 |
| plan_feed (shed two) | 3.1 | 4.5 | 5.6 |
| Simulator turn (backend) | 5.3 | 6.3 | 7.7 |

Contract tests over HTTP (n=40, file-less store): get_farm_profile p95 32.6 ms, set_farm_mode p95 35.1 ms.
All within the 500 ms budget. The file-backed store was not separately benchmarked; its E2E round trips above were
4–39 ms (the 38.9 ms one was the first call after a restart).

## 5. Found on the way

- The first concurrency test hung: the test client reused one JSON-RPC id for 5 in-flight requests. The SDK silently
  never answers the overwritten ones (FRICTION_LOG FL-011). Fixed in the test; the change was still applied once.
- A stale `proposal_id` for the mode the farm already has would have produced a pointless "switch" read-back; now it
  changes nothing and says so (`repropose=False`), covered by a contract test and a mutant.

## 6. Independent review (fresh agent, read cold against DESIGN §5–§7, §12, §13, §15)

No path applied a change without a live, exactly matching "yes". Findings and fixes:

| Sev | Finding | Fix | Regression test |
|---|---|---|---|
| Medium | A failed `COMMIT` left the connection inside the transaction (every later write failed; reads saw uncommitted data) | ROLLBACK, then re-raise | `test_a_failed_commit_rolls_back_and_the_store_stays_usable` |
| Medium | "no" repeated after the change was applied was answered "Done …" | Decision NOTHING, reason `already_done`: "That change was already made earlier, so saying no now doesn't undo it." + how to undo | decide table + `test_no_after_the_change_was_made_is_not_answered_with_done` |
| Medium | "switch to contract" (pending), then "switch to independent" (already so) left the first read-back confirmable | the already-set answer withdraws older pending read-backs (§5.1 point 5); the check runs inside the transaction | `test_a_newer_request_…withdraws…`, `test_the_latest_request_replaces_an_older_read_back` ([09](2026-09-28_farm_profile/09_latest-request-replaces-read-back.png)) |
| Low | Confirmed + "no" + other arguments produced a new read-back | a "no" never proposes | table test over every status |
| Low | "Already in place" read outside the transaction | moved inside (`in_place` callback) | covered above |
| Low | Simulator: a slow read-back could become pending after the farmer had moved on | turn counter: only the latest turn may leave a read-back pending | reasoned (not reproducible from one page, which blocks overlapping turns) |
| Low | "we're not a contract farm" / "change the feed in my own shed 2" matched a switch; bare "ha" counted as yes | negation guard; "own" only as "own farm"; "ha" removed | intent tests |
| Low | Relative `CLUCKTALK_STATE_PATH` resolved per working directory | relative paths anchored at the repo root; config accepts only a `.sqlite3` file | `test_state_path_default_relative_and_suffix` |
| Minor | Contract plan said `price_is_simulated: true` with no price | false when there is no price | `test_contract_plan_flags_no_simulated_price` |

Not changed: help always offers "Switch my farm to contract farming" as an example, also on a contract farm (help
examples are static per tool today).

After the fixes, a short Simulator rerun: help sentence ends cleanly; "switch to contract" → read-back; "switch to
independent farming" → "already … nothing changed"; "yes" → nothing pending, no tool call; "we're not a contract
farm" → host fallback, no switch; "switch to contract" → "haan" → "Done. Your farm is now set up as a contract farm."

## 7. Not done here

- 31 new Telugu strings are pending native review (docs/TELUGU_REVIEW.md §1; 57 pending in total).
- `eval-fast` does not exist yet (golden suite: 11 Oct), so there is no score delta to report.
- Contract terms (`set_contract_terms`), the supervisor feed request, and the contract demo scenario are 8 Oct work.
