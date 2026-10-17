# Product feedback: paste-ready copy

Ten plain-text blocks for the Devpost product-feedback fields, one per tool, each under 110 words, in the builder's own words. The heading line is not part of the block. The long version with the sources is `docs/PRODUCT_FEEDBACK.md`; FL numbers are in `FRICTION_LOG.md` (or `docs/DEV_NOTES.md` for my own tooling), FR numbers in `FEATURE_REQUESTS.md`. Every FL and FR number and every count below was checked against those files and the tests on 7 October 2026 (blocks 3 and 4 updated on 13 October 2026). Which file goes in which Devpost field: the ten blocks below go in the product-feedback fields, one per tool; the short friction copy is `docs/DEVPOST_FRICTION_PASTE_SHORT.md`; the long files (`docs/PRODUCT_FEEDBACK.md`, `docs/DEVPOST_FRICTION_PASTE.md`) are the evidence behind them. Where a sentence is marked builder-reported, the source is the builder's own report and not a file in this repository.

## 1. Amazon Bedrock and the Nova 2 Lite model

Amazon Bedrock and the Nova 2 Lite model. Used for: the optional AI triage step. Four live calls (29 September), none through the server; mock mode is the default. Worked well: once access worked, the call was simple. Needs work: models showed AVAILABLE with every quota at zero; a hidden verification refused the first call (FL-014); a billing error did not name the setting (FL-015); on my newer account every Nova quota was 0 and server-path calls were throttled (FL-031). Onboarding: 1 day from first attempt to first successful call (28 to 29 September), after quota requests. Build again: yes, if quotas and access were visible up front.

## 2. AWS CLI and boto3 on Windows

AWS CLI and boto3 on Windows. Used for: model-access checks and the few Nova calls. Worked well: the Converse toolChoice and image formats could be read in the installed botocore service model before any paid call. Needs work: the AWS CLI crashed on Windows while writing a reply that contained an emoji to a file, and left a truncated file (FL-019). Onboarding: the CLI installs without admin rights, and sign-in used IAM Identity Center, so no access keys. Build again: yes.

## 3. AWS console, accounts, credits and hosting options

AWS console, accounts, credits and hosting options. Used for: billing and credits; since 13 October the pilot runs on one Lightsail server in Mumbai (about $7 a month). Worked well: a server, static IP and firewall were enough. Needs work: port 443 closed by default; instance name cannot be changed; account plan not visible on an India account (FL-013, FR-007); App Runner closed to new customers 30 April 2026 (FL-027). Onboarding: new account plus credit about 1 hour; earlier sign-in problems on 7 October, on a previous account, were a separate issue (time not measured). Build again: yes (AWS, Lightsail). Builder-reported, 13 October.)

## 4. Alexa+ MCP documentation (QuickStart and Local Inspector)

Alexa+ MCP documentation (QuickStart and Local Inspector). Used for: an MCP server and a simulated Alexa+ experience, from the QuickStart (10 Jul) and Local Inspector (3 Aug) pages. Worked well: the addon.json schema, authentication checklist and 500 ms target are clear. Needs work: no minimum protocolVersion is stated while the Inspector example sends 2025-06-18 (FL-026); no self-serve Inspector (FL-024, FR-004); distributionCountries shows only US (FR-008). Onboarding: pages read quickly; testing on Alexa+ was not possible (partner-only, US-only, builder-reported). Build again: yes for MCP, with a caveat: access is partner-only and US-only, so I never ran on Alexa+; I would build again if access opens to individuals.

## 5. MCP Python SDK

MCP Python SDK. Used for: the server, 14 tools, Streamable HTTP and sessions. Worked well: my 29 protocol tests pass, and older protocol versions are answered with the requested version. Needs work: a duplicate JSON-RPC id can leave one request unanswered for 40+ seconds (FL-011); SDK error text echoed input until I wrapped it (FL-002, and F1 and F2 in SECURITY.md); tool errors need special handling because outputSchema validation and isError interact (FL-004). Onboarding: straightforward from the documentation and examples. Build again: yes, because every problem above had a workaround.

## 6. MCP Apps (ext-apps) and the basic host

MCP Apps (ext-apps) and the basic host. Used for: four HTML cards shown by the host (status, health check, sale plan, briefing). Worked well: the ui:// resource and _meta.ui.resourceUri model is clear. Needs work: the default CSP has no font-src, which blocks even an inlined Telugu font (FL-007); Alexa+ documents no card container size (FL-009); the Python SDK dropped extensions on 2025-11-25 (FL-008); the basic-host build needed bun and its install script (FL-021). Onboarding: the examples helped; Windows setup took extra steps, about 20 minutes (FL-021). Build again: yes.

## 7. Claude Code and the Claude models

Claude Code and the Claude models. Used for: building the whole project tests-first, with mutation checks and independent reviews by separate sessions. Worked well: the reviews found real bugs in pilot-mode code, fixed with regression tests (same-day deaths silently replaced, an optional MCP token, a session limit that is now least-recently-used eviction); many small local commits kept the work recoverable. Needs work: the shell tool changed backslash sequences in written files (FL-022); Windows line endings made a card bundle differ from the CI build (FL-025). Onboarding: fast to start; it needed strict rules and tests to stay safe. Build again: yes, with those rules, tests and an independent review.

## 8. Agent Skills format

Agent Skills format. Used for: packaging my tool-routing and safety rules as a skill (skills/clucktalk). Worked well: the folder format is simple. Needs work: I never loaded the skill in any agent; Claude Code's install path was not tested as a separate step, and the Kiro, Cursor and Copilot paths are marked unverified in the README. Onboarding: short (time not recorded). Build again: yes, the folder format is simple.

## 9. Tailscale Funnel (free hosting tunnel for the pilot)

Tailscale Funnel (free hosting tunnel for the pilot). Used for: a free HTTPS link from the builder's PC to one farmer's phone (builder-reported). Worked well: it worked on the first try after enabling HTTPS certificates and Funnel in the admin console (builder-reported). Needs work: I did not examine what the relay can see, and the PC's uptime is the real limit. Onboarding: short. Build again: yes for pilots.

## 10. GitHub Actions

GitHub Actions. Used for: CI on Windows and Linux. Worked well: it caught two problems the local Windows run missed (FL-023, FL-025). Needs work: the free minutes ran out while the repository was private (builder-reported), so from 7 October every commit used [skip ci] and was not CI-checked. Onboarding: easy (time not recorded). Build again: yes, now that the repository is public.
