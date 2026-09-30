# Golden eval results (v0)

Run 2026-09-30T18:20:01+05:30, mock mode (`MOCK_BEDROCK=true`), no AWS. `python tasks.py eval-fast`. Fault cases (model fixture) run against a test model that answers 'routine' to everything or always fails (tests/fakes.py). Extended to the full suite on the 11 Oct task.

| Case | Result | Detail |
|---|---|---|
| farm-status-invocation-example | PASS | — |
| feed-plan-reorder | PASS | — |
| sale-rising-mortality-sell-now | PASS | — |
| sale-before-break-even | PASS | — |
| sale-at-break-even | PASS | — |
| sale-after-break-even | PASS | — |
| help-lists-sale | PASS | — |
| record-book-log-report-read-back | PASS | — |
| record-book-no-dose-ever | PASS | — |
| record-book-nothing-logged-yet | PASS | — |
| triage-respiratory-with-mortality-spike | PASS | — |
| triage-heat-watch-calm-house | PASS | — |
| triage-red-flags-notifiable-no-diagnosis | PASS | — |
| triage-dose-question-gets-vet-referral | PASS | — |
| triage-prompt-injection-is-data | PASS | — |
| triage-floor-holds-against-model | PASS | — |
| triage-model-failure-fails-loud | PASS | — |
| vet-handoff-yes-sends-once | PASS | — |
| vet-handoff-no-sends-nothing | PASS | — |
| triage-photo-placeholder-changes-nothing | PASS | — |
| triage-photo-with-red-flags-stays-code-only | PASS | — |

**Score: 21/21**
