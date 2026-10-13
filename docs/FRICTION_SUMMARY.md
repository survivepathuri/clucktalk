# What I would most like the Amazon teams to read

One page from `FRICTION_LOG.md`: the five priority entries, then two runner-ups. Each has three lines: who is affected, what it cost me (only costs that were recorded; anything else says "not recorded"), and the change I ask for with its feature request in `FEATURE_REQUESTS.md`. The full entries, with steps and evidence, are in the log and in `docs/DEVPOST_FRICTION_PASTE.md`.

## The five priority entries

### FL-014: Bedrock on a new account: "AVAILABLE" models with every quota at 0, then an account-verification gate
- **Who is affected:** anyone making a first Bedrock call from a new AWS account (mine: a new AWS India account, us-east-1).
- **What it cost me:** two Support cases opened about 28 September and answered 28 to 29 September; the first real call was refused by account verification on 29 September and worked on the retry about two hours later; demo mode stayed the working path. Hands-on time: not recorded.
- **What I ask:** return the applied inference quota and an account-verification status in `GetFoundationModelAvailability` and on the model catalog page, and have quota-increase replies state the new quota per model (FR-006).

### FL-024: No self-serve Alexa AI CLI or Local Inspector for hackathon participants
- **Who is affected:** hackathon participants building an Alexa+ add-on, especially on Windows.
- **What it cost me:** the official validation was never run; I built my own replay of the documented flow (`python tasks.py inspector-replay`) and a self-check (`python tasks.py readiness`) and say they are mine. Time: not recorded.
- **What I ask:** a participant access path named on the hackathon Resources page, or a public Local Inspector install guide, and a statement on Windows 11 support (FR-004).

### FL-009: No MCP Apps rendering profile for Alexa+ (container size, `ui/*` messages, CSP, fonts)
- **Who is affected:** builders designing cards for Echo Show, phone and web, and anyone whose cards use Indic scripts.
- **What it cost me:** device sizes had to come from APL docs written for skills; the card was checked at four sizes in my Simulator, and nothing at 11 inches and above. Time: not recorded.
- **What I ask:** one "MCP Apps on Alexa+" page with the container size and display modes per device class, the supported `ui/*` messages, the CSP and the font policy (FR-002).

### FL-017: No word on proactive notifications or household identity for MCP add-ons
- **Who is affected:** builders planning reminders, or a flow where more than one person in a household uses the add-on.
- **What it cost me:** alerts were designed pull-only (heard on the next briefing), and each person needs their own linked account. Time: not recorded.
- **What I ask:** a yes or no on proactive notifications from MCP add-ons, and which request fields, if any, tell household members apart, on the MCP Toolkit Overview and Account Linking pages (FR-005).

### FL-013: AWS India (AISPL) account: no plan shown in the console; credit rules for Marketplace models missing
- **Who is affected:** builders with an AWS account sold by AWS India.
- **What it cost me:** the plan could only be found with `aws freetier get-account-plan-state` after a CLI login; the workaround is to set Pay by Invoice before the first Claude call and keep Nova as the fallback model. Time: not recorded.
- **What I ask:** show the account plan on the Billing home for every account (or say why not for AISPL), and state whether promotional credits cover Marketplace-billed Bedrock models (FR-007).

## Runner-ups

### FL-007: MCP Apps default CSP blocks even an inlined font; whether a blocked font source falls through is undocumented
- **Who is affected:** card builders who must ship their own font, such as Telugu, under a strict host.
- **What it cost me:** a strict-CSP probe had to be built and run in Chrome to learn the fall-through; the cards inline the font, fall back to system fonts and send a warning. Time: not recorded.
- **What I ask:** `font-src 'self' data:` in the spec's default CSP or a fonts field, and an answer from the Alexa+ team on whether its renderer applies the default CSP literally (FR-003).

### FL-027: AWS App Runner no longer accepts new customers; the documentation recommends ECS Express Mode
- **Who is affected:** builders choosing App Runner as new customers after 30 April 2026 (builder-reported, from the AWS documentation page "AWS App Runner availability change").
- **What it cost me:** not recorded; the page was read while choosing hosting, and App Runner was not used.
- **What I ask:** keep the 30 April 2026 change and the ECS Express Mode link at the top of every App Runner getting-started page. No feature request is filed for it yet.
