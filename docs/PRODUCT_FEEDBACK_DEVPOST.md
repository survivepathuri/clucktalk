# Product feedback: paste-ready copy (final, 2026-10-19)

Ten plain-text blocks, each 110 words or fewer; the heading line is not part of the block.

## 1. Amazon Bedrock, Nova 2 Lite (Converse API)

Amazon Bedrock, Nova 2 Lite. Used for: triage and briefing slow paths via Converse; the pilot runs with it off. Worked well: four real calls on 29 Sep 2026 succeeded: 2,342 input and 106 output tokens, $0.000000. Needs work: models showed available while every quota was 0, then an account-verification error blocked the first call (FL-014); ThrottlingException says only "Too many requests" (FL-031). Onboarding: about 2 hours of work to unblock the first call (quota and account verification, solved with Claude Code's help); the account was created on 28 September and the first successful calls were on 29 September. Build again: yes, with invocation logging from day one.

## 2. Amazon Lightsail

Amazon Lightsail. Used for: hosting the farmer pilot on one Mumbai instance (Ubuntu 24.04, static IP, about $7 a month, paid by card). Worked well: the deploy and verify scripts ran twice on the real server, and the app, HTTPS proxy and backup timer came back after a reboot. Needs work: port 443 is closed on a new instance; the instance name cannot be changed; the console key download is a one-time secret (FL-030); memory under real load is untested. Onboarding: about 5 hours from creating the instance to the first deploy. Build again: yes.

## 3. Alexa+ MCP documentation and our Simulator

Alexa+ MCP documentation and our Simulator. Used for: building an MCP server to the published guidance (QuickStart, 10 Jul; Local Inspector, 3 Aug); we wrote our own Simulator because we could not run on Alexa+. Worked well: the QuickStart gave the transport, the auth checklist and the 500 ms target. Needs work: no self-serve way to run the Alexa AI CLI or Local Inspector (FL-024); no stated protocolVersion (FL-026); no card size, CSP or font guidance (FL-009). Onboarding: about 2 hours reading the docs; we never tested on real Alexa+. Build again: yes, we would build for MCP again.

## 4. AWS CLI and boto3 (Windows)

AWS CLI and boto3 on Windows. Used for: Identity Center sign-in, plan and quota checks, a hello call to Bedrock, and the live client in our code. Worked well: no access keys were needed, and we read the Converse request shapes in the installed botocore model before any paid call. Needs work: the CLI crashed on Windows while saving a reply with an emoji and left a truncated file (FL-019); a billing error did not name the setting to change (FL-015); an aws login profile needed botocore[crt] (FL-032, details not recorded). Onboarding: about 60 minutes from install to a working aws sts get-caller-identity.

## 5. MCP Python SDK (mcp 2.2.0)

MCP Python SDK (mcp 2.2.0). Used for: the server, 14 tools over Streamable HTTP with sessions. Worked well: our 29 protocol tests pass against it, and it answers initialize for four protocol versions. Needs work: two in-flight requests with the same id leave one unanswered with no error (FL-011); default tool errors name the tool and fields (FL-002); middleware results leak resultType onto the 2025-11-25 wire (FL-001). Onboarding: not easy from the docs alone; we worked it out by brainstorming with Claude Code, about 2 hours.

## 6. MCP Apps (ext-apps) and its reference host

MCP Apps (ext-apps) and its reference host. Used for: four HTML cards (status, health check, sale plan, briefing) written against the postMessage protocol with no JS SDK; we built the basic-host to test them. Worked well: a view needs no SDK, so the cards have no Node build. Needs work: the spec example and schema disagree on appInfo (FL-006); the default CSP blocks even an inlined Telugu font (FL-007); the basic-host build needs bun and a built repo root (FL-021). Onboarding: about 20 minutes to build the host. Build again: yes.

## 7. Agent Skill

Agent Skill. Used for: packaging our tool-routing and safety rules in skills/clucktalk. Worked well: tests keep the skill in step with the server. Needs work: we never loaded it in an agent, so we cannot say whether an agent picks it up; each agent uses a different install folder. Onboarding: about 8 hours to the first working SKILL.md.

## 8. GitHub Actions

GitHub Actions. Used for: running our full check on Ubuntu and Windows with Python 3.12 and 3.13. Worked well: it caught two problems the local Windows run missed (FL-023, FL-025). Needs work: the macOS job is manual-only because of its minute cost. We used [skip ci] on 23 of 186 commits (7 to 13 Oct) because free CI minutes ran out, so those commits were not CI-checked. The last CI run, on commit 1f0a12c, passed. Onboarding: time not recorded.

## 9. Claude Code

Claude Code. Used for: writing and checking the code, and for independent review passes by fresh sessions that read the code cold. Worked well: ten recorded review rounds found real defects, each fixed with a regression test. Needs work: the shell tool turned a backslash sequence into an invisible backspace character in a source file (FL-022); the reviewers are AI agents, not a human audit. Onboarding: it took a long time before it was productive on this repo; we did not time it. Build again: yes.

## 10. Caddy, Let's Encrypt and sslip.io (optional; not an Amazon tool)

Caddy, Let's Encrypt and sslip.io (optional; not an Amazon tool). Used for: HTTPS for the farmer page on the Lightsail server without buying a domain. Worked well: the certificate was issued, is valid to 2027-01-10, and the proxy came back after a reboot. Needs work: no problem or surprise; the pilot depends on a free third-party name service. Onboarding: time not recorded.

Not used in the submitted build: Polly, Lambda, DynamoDB, CloudFront, S3 Vectors, OpenSearch, SMS (the vet SMS is simulated).
