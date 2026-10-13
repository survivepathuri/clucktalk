# Independent reviews

After each main feature, a fresh agent with no memory of building it read the code cold and tried to break it, against the design rules in `docs/DESIGN.md` (section 5 tool contract, section 6 behavior, section 7 safety, section 12 pitfalls). Its findings were reported first. Then the builder decided which to fix, and each fix was written test-first with a regression test. This page summarizes the rounds. The same table is in machine-readable form in `data/results/review_rounds.json` and shown in `docs/RESULTS.md`.

**What this is and is not.** The reviewer is an AI agent, not a human security auditor, a vet or Amazon. A review finds what it was pointed at. The record below comes from the builder's own progress log; no outside party has checked it. A count appears only where the log records one.

## The rounds

| # | Scope | Found (reviewer's severity) | Status |
|---|---|---|---|
| 1 | `get_farm_status` and `plan_feed`: the domain layer and the two tools | 2 High, 6 Medium, several Low, 3 suspicions | All fixed with regression tests. A second pass resolved 11 of 13, and the 2 partial and 3 new Low findings were fixed too. One limit documented: the top-level status text is built from per-finding texts that are each checked, not checked again as a whole. |
| 2 | The MCP App card and the Simulator | 2 Medium, 9 Low, 1 risk | All fixed or documented. Mutation check of the fixes: 8 of 8 caught. One server change came out of it: the number formatter keeps the sign for values between -1 and 0. |
| 3 | Farm profile, the confirmation pattern and the write path | 3 Medium, 5 Low, 1 minor | All fixed with regression tests except two: a Simulator overlapping-turn race (fixed, reasoned only, no test reproduces it) and a static help example on a contract farm (documented). |
| 4 | Voice record book (three steps) | 1 Critical, 4 Medium or Medium-High, 1 Low-Medium | All fixed. The Critical one: a backdated correction was never checked against deaths already on file for later days, so it could push the total over the birds placed while saying it was saved. Regression test added. |
| 5 | `plan_sale` and `set_contract_terms` | 1 High, 1 Info | The High fixed: contract mode leaked market-price rupee numbers into structured content although nothing spoke them. The Info item (a sale-by-weight error that the demo cannot reach) documented as intended. |
| 6 | Health triage and the vet handoff, first round | 1 High, 3 Medium, 5 Low | All fixed with regression tests. |
| 7 | Health triage, second round (2026-09-30) | 1 High, 2 Medium, 7 Low | The High fixed: words that matched no known sign got the lowest urgency ("doesn't look urgent") even when they described a red flag. Now such words are treated as urgent and never lowered. Both Medium fixed (a late model reply flipped a timed-out check; a billed reply with no tool call was ledgered as zero tokens). 3 Low fixed. 4 Low deliberately not fixed, by the builder's decision. |
| 8 | Daily briefing (2026-09-30) | 2 High, 4 Medium, Low items (named H1, H2, M1 to M4, L1 to L4 in the log) | H1, H2 (a stored model ordering that cannot be read is now shown as such and rebuilt), M1 (the model can reorder only non-health items), M2, M3 (a reportable check stays on the briefing) and L1 fixed; M4 only if its reproduction test failed; L2 to L4 deliberately not fixed. |
| 9 | Flock follow-up agent, safety review (2026-10-01) | Findings named B1, H1 to H4, M3, M5, M6, M8, L2 to L4 in the log; the full list is not copied | B1, H1, H4 fixed in commits `5b3bde1`, `08f7d7f`, `dfc9996`. H3 fixed in `e0a5397` (an urgent or reportable follow-up stays visible after a newer, lower check). H2 fixed in `c2d73c0` (a spike logged on the check day after the check now counts). M5, M8 and L2 fixed in Step 47C (`92128ba` for L2). M3 documented only. L3 and L4 cut by decision. The first stage of M6 shipped as the structured `safety` field on the briefing and the status, and the briefing and the status were made to agree in `4eba878`. |
| 10 | Pilot mode, commit `0bd9905` (2026-10-06 to 2026-10-07) | The log records no count. The fixes fall into four groups. | Fixed in four commits, `80d141d`, `32c3182`, `b397d3a`, `ccdbf76`. See below. |

## What the pilot review changed (round 10)

- **Same-day deaths** were assumed to add up or replace silently. The pilot now shows the old and the new number and asks "add" or "replace" (`docs/SAFETY_MATRIX.md`, row 10).
- **Pilot access.** The MCP server refuses to start in pilot mode without a strong token, and the farmer's token must differ from the Simulator's. A new session makes room by dropping the least recently used one. Every pilot answer carries security headers. The health check says only "ok" or "not ok".
- **The Telugu matcher and the first-open notice.** A polite word after yes or no is accepted; a minus sign makes the input "not understood"; a one-screen notice with seven items must be acknowledged before anything works.
- **Operations.** The backup script writes its stamp only after an integrity-checked copy, and `pilot-stats --backups` warns when the last good backup is older than 26 hours.

## What stayed open after the reviews

- **Telugu:** 86 of 434 strings reviewed by the builder, a native Telugu speaker; 348 pending (including the pilot page); no independent review. (`docs/TELUGU_REVIEW.md`)
- **At the time of the review, nothing had run on a server, a phone or a real browser for the pilot**, and this repository records no browser test since. The page's logic is tested in Node against a hand-made DOM (`tests/harness/pilot_page_checks.js`), which is not a browser test.
- **Two hardening options** (`MemoryDenyWriteExecute` and `SystemCallFilter` in the Linux service units) were skipped on purpose, because they can stop a Python service starting. They are untested.
- **No human security audit** and no veterinary review exist. See `SECURITY.md` and `docs/PRODUCTION_PATH.md`.

## Other checks that are not independent reviews

Mutation checks (a script plants a fault; the tests must catch it) are the builder's own and are listed in `docs/RESULTS.md`. Property tests, fuzz tests and concurrency tests are in `tests/`. They are not reviews by someone else.
