# Product feedback: paste-ready copy

One plain-text block per tool for the Devpost product-feedback fields, each under 110 words. The heading line is not part of the block. The sources and the long version are in `docs/PRODUCT_FEEDBACK.md`; FL numbers are in `FRICTION_LOG.md`, FR numbers in `FEATURE_REQUESTS.md`. Placeholders that start with "BUILDER TO CONFIRM" stay until the builder answers them; all of them are listed at the end.

## 1. AWS services: what was live and what was mocked

Live: Amazon Bedrock Runtime converse with Amazon Nova 2 Lite in us-east-1, a handful of one-off calls from the AWS CLI and boto3 (a hello call, then two forced-tool-choice spike calls). Also used: Service Quotas, AWS Support cases (FL-014) and an IAM Identity Center role for the CLI. Mocked: every AI answer in the demo, evals and tests (MOCK_BEDROCK=true, a "Demo data" badge); the server's live-AI path was not verified end to end. Nothing was deployed to AWS: no Lambda, no Polly, no Knowledge Base, never OpenSearch Serverless. Read or attempted, not used (builder-reported): Lightsail and App Runner docs, console sign-in, the credit request.

## 2. Amazon Bedrock and Amazon Nova 2 Lite

Used for: our agents' optional live AI mode; in practice a hello call and a two-call spike. Worked well: latencyMs 450; forced toolChoice worked with text and an image. Needs work: models showed AVAILABLE with every quota at 0, Support gave no numbers, and an undocumented verification gate refused the first call (FL-014); Anthropic models stayed blocked by their Marketplace agreement; Nova read blue as white once (FL-020). Onboarding: first reply 29 Sep. [BUILDER TO CONFIRM: How did onboarding to Bedrock and Nova 2 Lite feel?] Again: [BUILDER TO CONFIRM: Build with Bedrock and Nova 2 Lite again? Yes or no, and why?]

## 3. AWS CLI v2 and boto3 on Windows

Used for: key-free sign-in, account and quota checks and the hello call (CLI 2.37.4); the spike and live path (boto3 1.43.103). Worked well: no access keys; get-account-plan-state showed the plan the console did not. Needs work: an emoji in a reply crashed the CLI's Windows output and left a truncated file (FL-019); get-credits says "IAM user access not activated" to an Identity Center role (FL-015); the recommended setup silently upgrades a Free-plan account (FL-012). [BUILDER TO CONFIRM: How did installing the AWS CLI and signing in with IAM Identity Center feel?] Again: [BUILDER TO CONFIRM: Use the AWS CLI and boto3 again? Yes or no, and why?]

## 4. AWS Lightsail, AWS App Runner, Free Tier credits, console and account

Read or attempted, not used (builder-reported, 7 October). Console: authenticator codes rejected; with several accounts, unclear which held the credits; recovery postponed (FL-027). App Runner: no new customers since 30 April 2026; ECS Express Mode recommended (FL-027). Lightsail: in Mumbai (half the data transfer); trials replaced by Free Tier credits. Credit form submitted 7 October, pending. Time lost: [BUILDER TO CONFIRM: How many hours did the AWS console sign-in problem on 7 October cost?] [BUILDER TO CONFIRM: How did choosing AWS hosting and requesting the credits feel?] Again: [BUILDER TO CONFIRM: Try AWS hosting (Lightsail or ECS Express Mode) again once access is back? Yes or no, and why?]

## 5. Alexa+ MCP documentation (QuickStart, Local Inspector)

Used for: building to Amazon's guidance; the Local Inspector and Builder Tools were not used. Worked well: the QuickStart gave the transport, auth checklist, latency target and addon.json schema. Needs work: no self-serve Local Inspector or Alexa AI CLI for participants (an account provided to an Alexa Solutions Architect, macOS or Ubuntu only, a login-gated guide; FL-024); no protocolVersion stated; the Inspector example sends 2025-06-18 (FL-026); no card size, CSP or fonts (FL-009); nothing on proactive notifications or household identity (FL-017). [BUILDER TO CONFIRM: How did getting started from the Alexa+ MCP QuickStart feel?] Again: [BUILDER TO CONFIRM: Build an Alexa+ add-on again? Yes or no, and why?]

## 6. The simulated Alexa+ path (our Simulator)

Used for: playing the Alexa+ client role with Echo Show and Echo Dot modes, cards and a panel showing the exact MCP wire; it is our code, not Amazon's. Worked well: it speaks the tool's own text, so card and spoken numbers match (tested), and the golden evals run against a real MCP server over HTTP. Needs work: that match holds only in the Simulator, because Alexa+ composes its own speech; the intent layer is rules, not Alexa+'s tool choice. Onboarding: not applicable (python tasks.py run). Again: [BUILDER TO CONFIRM: Build a simulated Alexa+ client again before having device access? Yes or no, and why?]

## 7. MCP Python SDK (mcp 2.2.0)

Used for: the Streamable HTTP server, tools, middleware and card resources. Worked well: Apps support is in-core; 2025-11-25 and three older versions negotiate. Needs work: middleware results leak resultType (FL-001); default errors name the tool and fields, with no hook (FL-002); the localhost Origin allow-list accepts every port (FL-003); extensions dropped on 2025-11-25 (FL-008); a duplicate in-flight id leaves a request silently unanswered for 40 seconds or more (FL-011). [BUILDER TO CONFIRM: How did going from zero to a first tool call with the MCP Python SDK feel?] Again: [BUILDER TO CONFIRM: Build with the MCP Python SDK again? Yes or no, and why?]

## 8. MCP Apps spec and the ext-apps basic-host

Used for: four cards written against the postMessage protocol without the JS SDK, and the reference basic-host to test them. Worked well: no SDK or Node build for cards. Needs work: the spec example sends clientInfo where the schema requires appInfo (FL-006); the default CSP blocks even an inlined data: font while the reference host allows it, and fall-through is undocumented (FL-007); the basic-host needs an undocumented root build and bun (FL-021, about 20 minutes). [BUILDER TO CONFIRM: How did building MCP Apps cards and running the reference host feel?] Again: [BUILDER TO CONFIRM: Build MCP Apps cards again? Yes or no, and why?]

## 9. MCP Inspector 2.8.0 CLI

Used for: capturing evidence of tool calls and error results, as a stand-in for the Alexa+ Local Inspector we could not run. Worked well: tools/list and tools/call captured our evidence; successful calls exit 0. Needs work: on Windows the CLI crashes with a libuv assertion after an error result, so the exit code is unusable (FL-005); it validates an error's structuredContent against the success schema, unlike the Python SDK client (FL-004). [BUILDER TO CONFIRM: How did getting the MCP Inspector CLI running feel?] Again: [BUILDER TO CONFIRM: Use the MCP Inspector CLI again? Yes or no, and why?]

## 10. Claude Code and the Claude models

Used for: writing and checking the code, and ten independent review rounds by fresh agents that read the code cold; the model version per session is not recorded. Worked well: the reviews found real defects, including a Critical record-book bug (total deaths could exceed birds placed while saying "saved") and a High triage bug, each fixed with a regression test. Needs work: the shell tool turned a backslash sequence into an invisible backspace character in a written file, and it recurred (FL-022). [BUILDER TO CONFIRM: How did starting this project with Claude Code feel?] Again: [BUILDER TO CONFIRM: Build with Claude Code again? Yes or no, and why?]

## 11. The Agent Skills format

Used for: skills/clucktalk, a SKILL.md plus three reference files that teach a coding agent to operate the 14 tools. Worked well: one folder matches the layout that Kiro's and Cursor's docs describe; tests keep it in step with the server. Needs work: every agent uses a different install folder, the Copilot path was seen only on a third-party page, and the skill was never loaded in any agent. [BUILDER TO CONFIRM: How did writing the Agent Skill feel?] Again: [BUILDER TO CONFIRM: Write an Agent Skill again? Yes or no, and why?]

## 12. Hypothesis

Used for: property and fuzz tests (dev only). Worked well: the fuzz round found protocol errors that echoed input back (F1, F2), and fuzz tests pin an SDK behaviour (F3) and our shed-name reader (F4). Needs work: nothing recorded. [BUILDER TO CONFIRM: How did adding Hypothesis tests feel?] Again: [BUILDER TO CONFIRM: Use Hypothesis again? Yes or no, and why?]

## 13. Tailscale Funnel

Used for: publishing the farmer pilot page from the builder's own PC, because AWS access was unavailable (builder-reported); the MCP port stays on the loopback. Worked well: it worked on the first try after HTTPS certificates and Funnel were enabled in the admin console (builder-reported). Needs work: what the relay can see was not examined; availability depends on that PC and its internet. Again: [BUILDER TO CONFIRM: Use Tailscale Funnel again for a pilot like this? Yes or no, and why?]

## 14. GitHub Actions

Used for: lint, tests and scans on ubuntu and windows with Python 3.12 and 3.13. Worked well: CI caught two failures the local Windows run did not (FL-023, FL-025). Needs work: the macOS job is manual-only because it uses about 50 quota minutes per run; the repository is private until it is made public. [BUILDER TO CONFIRM: How did setting up GitHub Actions for this repository feel?] Again: [BUILDER TO CONFIRM: Use GitHub Actions again? Yes or no, and why?]

## 15. Other libraries (Starlette, uvicorn, pydantic, jsonschema, httpx2, SQLite, Noto Sans Telugu, ruff, pytest)

Used for: the ASGI app, tool models, argument validation, the HTTP client, the farm state, Telugu on the cards, and lint and tests. Worked well and needs work: nothing recorded, apart from the inlined Telugu font under a strict CSP (FL-007). [BUILDER TO CONFIRM: Anything to add about onboarding for the other libraries, or nothing to add?] Again: [BUILDER TO CONFIRM: Use the other libraries again? Yes or no, and why?]

## QUESTIONS FOR THE BUILDER

Every placeholder above and in `docs/PRODUCT_FEEDBACK.md`, in order, so they can be answered in one message.

1. How did onboarding to Bedrock and Nova 2 Lite feel?
2. Build with Bedrock and Nova 2 Lite again? Yes or no, and why?
3. How did installing the AWS CLI and signing in with IAM Identity Center feel?
4. Use the AWS CLI and boto3 again? Yes or no, and why?
5. How many hours did the AWS console sign-in problem on 7 October cost?
6. How did choosing AWS hosting and requesting the credits feel?
7. Try AWS hosting (Lightsail or ECS Express Mode) again once access is back? Yes or no, and why?
8. How did getting started from the Alexa+ MCP QuickStart feel?
9. Build an Alexa+ add-on again? Yes or no, and why?
10. Build a simulated Alexa+ client again before having device access? Yes or no, and why?
11. How did going from zero to a first tool call with the MCP Python SDK feel?
12. Build with the MCP Python SDK again? Yes or no, and why?
13. How did building MCP Apps cards and running the reference host feel?
14. Build MCP Apps cards again? Yes or no, and why?
15. How did getting the MCP Inspector CLI running feel?
16. Use the MCP Inspector CLI again? Yes or no, and why?
17. How did starting this project with Claude Code feel?
18. Build with Claude Code again? Yes or no, and why?
19. How did writing the Agent Skill feel?
20. Write an Agent Skill again? Yes or no, and why?
21. How did adding Hypothesis tests feel?
22. Use Hypothesis again? Yes or no, and why?
23. Use Tailscale Funnel again for a pilot like this? Yes or no, and why?
24. How did setting up GitHub Actions for this repository feel?
25. Use GitHub Actions again? Yes or no, and why?
26. Anything to add about onboarding for the other libraries, or nothing to add?
27. Use the other libraries again? Yes or no, and why?
