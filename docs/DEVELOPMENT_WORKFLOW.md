# How CluckTalk was built

CluckTalk was built by one person (the builder) working with AI assistants. This page says who did what, which checks
stood between a change and the repository, and what those checks do not prove. It describes the process only; the
product's own limits are in the README and `docs/JUDGES.md`.

## Roles

| Who | What they did |
|---|---|
| The builder (human) | Chose the product and its scope, decided what to build in each phase, approved plans before large changes, took every decision about safety wording and scope, decided which review findings to fix, ran the pilot arrangements, supplied the farmer's rules, and is the only Telugu reader (86 of 476 strings approved; the rest are pending, see `docs/TELUGU_REVIEW.md`). |
| Claude Code (AI, in the repository) | Wrote and changed code, tests, docs and scripts in the repository under the rules in `CLAUDE.md`; ran the checks; recorded friction as it happened (`FRICTION_LOG.md`); wrote the evidence files in `docs/evidence/`. |
| Claude chat (AI, outside the repository) | Used by the builder for planning and drafting, as the builder describes it; this repository holds no transcript of those chats. Whatever it produced reached the repository through the builder and Claude Code. |
| Fresh review agents (AI) | Read finished features cold and tried to break them (see "Review gates"). |

No AI assistant decided scope, accepted a pilot, or confirmed anything with the farmer. The builder's own writing is
marked `[FILL]` in the Devpost draft where Claude Code was not meant to write it.

## Working rules

`CLAUDE.md` holds twelve build rules that every Claude Code session reads first. The ones that shaped the process:

- Mock first. Nothing is called live until the builder approves it (Rule 5, Rule 6). The four one-off live Amazon Bedrock calls were each approved by the builder first and are recorded in `docs/AWS_SETUP.md`.
- Never use Amazon OpenSearch Serverless; a script checks for it (Rule 1).
- Record friction at the moment it happens, never in a batch (Rule 2).
- A change is not done until the checks pass and the evidence is shown (Rules 3 and 5).
- Never weaken or delete a test to make it pass; if an expectation looks wrong, stop and ask (Rule 3).
- A large change or any change to the architecture needs a plan the builder approves first (Rule 8).
- A progress log is updated at the end of every session, so the next session does not start cold (Rule 10).

## Review gates

1. **`python tasks.py check`** after every change: lint, format, the three test suites (harness, unit, contract), the
   OpenSearch Serverless scan and the secret scan. On 2026-10-16 it passed with 3,403 tests.
2. **`python tasks.py eval-fast`**: 88 golden cases against a real MCP server over HTTP in mock mode, run after any
   tool, schema or prompt change (`docs/EVALS.md`). The score says nothing about live model answers.
3. **Mutation checks** on newer test sets: a scratch script plants faults and the tests must catch them. The scripts are
   not in the repository, so the counts in `docs/RESULTS.md` are copied from the builder's log and cannot be reproduced
   from a clone.
4. **Independent review rounds** after each main feature (`docs/INDEPENDENT_REVIEW.md`): a fresh AI agent with no memory
   of building the feature reads the code against `docs/DESIGN.md`, reports findings first, and the builder decides
   which to fix. Fixes are written test-first with a regression test. The reviewers were AI agents, not a human audit.
5. **Document audits.** Claims in the README, `docs/JUDGES.md` and the Devpost drafts were checked against the code and
   the saved outputs, and unsupported sentences were softened or removed. A last read-only audit before submission
   found stale numbers and a few overstated sentences, which were corrected in the commits that follow it.
6. **CI** (`.github/workflows/ci.yml`): `setup` and `check` on Ubuntu and Windows, Python 3.12 and 3.13. Some earlier commits
   were pushed with `[skip ci]`, so CI did not run on every commit. The README says which run was last recorded green.

## What this process does not show

- No human security audit, no privacy or data-law review, and no veterinary or agronomic review of the thresholds.
- No Alexa+ device and no Amazon review: the Alexa+ Simulator in this repository plays the client role.
- No farmer has used the pilot yet.
- The AI reviewers can miss what they were not pointed at, and the mutation counts are the builder's own record.
- Claude Code's account of a session is not evidence by itself; the evidence is the saved command output, tests and
  screenshots in `docs/evidence/` and `docs/proof/`.
