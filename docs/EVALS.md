# Golden eval results (v0)

Run 2026-10-04T01:57:33+05:30, mock mode (`MOCK_BEDROCK=true`), no AWS. `python tasks.py eval-fast`. Fault cases (model fixture) run against a test model that answers 'routine' to everything or always fails (tests/fakes.py). Extended to the full suite later.

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
| triage-unmapped-words-never-not-urgent | PASS | — |
| triage-model-failure-fails-loud | PASS | — |
| vet-handoff-yes-sends-once | PASS | — |
| vet-handoff-no-sends-nothing | PASS | — |
| triage-photo-placeholder-changes-nothing | PASS | — |
| triage-photo-with-red-flags-stays-code-only | PASS | — |
| briefing-demo-story-health-first | PASS | — |
| briefing-more-reads-the-rest | PASS | — |
| briefing-recalls-a-spike-from-yesterday | PASS | — |
| briefing-no-dose-or-drug-text | PASS | — |
| briefing-model-cannot-demote-health | PASS | — |
| briefing-model-tries-to-move-health-is-rejected | PASS | — |
| briefing-model-outage-fails-loud | PASS | — |
| briefing-shows-a-check-the-ai-could-not-finish | PASS | — |
| help-lists-briefing | PASS | — |
| followup-better-closes | PASS | — |
| followup-same-escalates | PASS | — |
| followup-worse-escalates-and-offers-the-vet | PASS | — |
| followup-not-sure-escalates | PASS | — |
| followup-record-book-spike-overrides-better | PASS | — |
| followup-no-answer-lapses-never-better | PASS | — |
| followup-relapse-after-better | PASS | — |
| followup-worse-after-the-vet-handoff-escalates-again | PASS | — |
| followup-tool-selection-shed-kotam-house | PASS | — |
| followup-answer-words-nahi-then-haan | PASS | — |
| followup-answer-words-vaddu-then-avunu | PASS | — |
| contract-terms-read-back-says-four-numbers | PASS | — |
| contract-terms-refuses-the-retired-mortality-argument | PASS | — |
| followup-urgent-check-keeps-its-warning-the-next-day | PASS | — |
| followup-reportable-check-keeps-its-warning-the-next-day | PASS | — |
| status-reportable-check-is-alert-never-doing-well | PASS | — |
| status-due-follow-up-is-watch-never-doing-well | PASS | — |
| status-escalated-follow-up-is-alert-never-doing-well | PASS | — |
| followup-worse-after-a-handoff-and-a-newer-check-still-says-contact-the-vet | PASS | — |
| followup-not-sure-after-a-handoff-and-a-newer-check-still-says-contact-the-vet | PASS | — |
| followup-urgent-stays-visible-after-a-newer-lower-check | PASS | — |
| followup-urgent-check-this-morning-stays-after-a-lower-check-this-afternoon | PASS | — |
| followup-spike-logged-after-the-check-the-same-day-overrides-better | PASS | — |
| followup-spike-already-in-the-check-is-not-news | PASS | — |
| followup-urgent-unanswered-does-not-lapse-on-day-eight | PASS | — |
| followup-watch-unanswered-still-lapses | PASS | — |
| safety-field-a-quiet-shed-is-ok-with-no-codes-and-no-vet-advice | PASS | — |
| safety-field-an-urgent-open-check-is-alert-and-advises-the-vet-on-status-and-briefing | PASS | — |
| safety-field-an-unanswered-urgent-follow-up-is-still-alert-and-advises-the-vet-on-day-twelve | PASS | — |
| safety-field-a-watch-check-is-watch-and-the-status-does-not-advise-the-vet | PASS | — |
| safety-field-the-briefing-and-the-whole-farm-status-agree-on-the-seeded-spike | PASS | — |
| safety-field-a-same-answer-to-a-watch-follow-up-escalates-and-advises-the-vet-on-the-status | PASS | — |
| safety-field-the-seeded-spike-advises-the-vet-on-the-status-of-shed-two-and-not-of-shed-one | PASS | — |
| safety-field-the-whole-farm-status-advises-the-vet-like-the-briefing-for-the-seeded-spike | PASS | — |

**Score: 65/65**
