# CluckTalk (కోడి మిత్ర)

The voice farm manager for India's **broiler** poultry farmers. A self-hosted MCP server (spec 2025-11-25,
Streamable HTTP) plus an Agent Skill, built for the Alexa+ add-on program.

> **Status**: in development. Nothing below is claimed working unless it has evidence in `docs/evidence/` or a
> passing check in `python tasks.py check` / `python tasks.py eval-fast`. See `docs/DESIGN.md` for the full design
> and what is built vs planned, and `docs/EVALS.md` for the current golden-suite score.

## Quick start (venv only; Docker is optional and never required)

Needs Python 3.12 or 3.13 (other versions from 3.11 run with a visible "untested" warning). Get it from
python.org, `brew install python@3.13` (macOS), `pyenv install 3.13`, or the deadsnakes PPA (Ubuntu).

Windows (cmd):

```
git clone <this repo>
cd CluckTalk
python tasks.py setup    :: creates .venv and installs pinned dependencies
python tasks.py run      :: starts the MCP server + the Alexa+ Simulator, opens http://127.0.0.1:8766/
```

Linux / macOS:

```
git clone <this repo>
cd CluckTalk
python3 tasks.py setup   # creates .venv and installs pinned dependencies
python3 tasks.py run     # starts the MCP server + the Alexa+ Simulator, opens http://127.0.0.1:8766/
python3 tasks.py check   # optional: lint + tests + AOSS check + secret scan
```

Set `CLUCKTALK_NO_BROWSER=1` to stop `run` from opening a browser. Node.js is optional: one card test
(`test_card_num_matches_the_server_formatter`) is skipped, with a reason, when `node` is not installed. The secret scan
in `check` needs a git checkout; on a ZIP download it prints "SKIPPED" and the rest of `check` still runs.

Try asking (typed or, if your browser supports it, spoken): *"How is shed two doing?"*, *"When should I sell shed
one?"*, *"How much feed does shed two need this week?"*, *"Switch my farm to contract farming"*.

Everything runs on seeded, clearly fictional demo data (`MOCK_BEDROCK=true`, shown as a "Demo data" badge). Live
mode (real Bedrock/Polly) needs an AWS account; see `docs/AWS_SETUP.md`.

## What it does today

- **Farm status** (`get_farm_status`) and **feed planning** (`plan_feed`) per shed, bilingual, with a card.
- **Sell-day plan** (`plan_sale`): the best day to sell a broiler shed, the break-even day, and why — or, for
  contract farmers, how each extra day changes FCR and the growing charge.
- **Farm profile** (`get_farm_profile`, `set_farm_mode`) and **contract terms** (`set_contract_terms`): switch
  between independent and contract farming, with an explicit read-back and "yes" before anything changes.
- **Daily briefing** (`get_daily_briefing`): the top things that need attention today, ranked, as a swipeable card. By
  voice it reads the top 3 and offers "more" (5 items at most). Health alerts always come first, decided by code; an
  AI model, only when live AI is switched on, may re-order the other items from a fixed list and can write no text.
  A death spike logged a few days ago still shows. A sale-window item is a simulated estimate and shows no rupees.
- **What can you do?** (`get_help`).
- A local **Alexa+ Simulator** (Echo Show / Echo Dot device modes, voice and text, a developer panel showing the
  exact MCP wire).

## Roadmap

- **Layer farming.** The domain layer already models egg-laying flocks (status, feed planning), but the current
  build, demo data and video target **broiler** farms only. Extending the voice/card experience to layer flocks
  the way broilers are covered today is future work.
- Voice record book, the full Contract Earnings Tracker (sensitivity/what-if), vaccination planner and vaccine-day
  coach, health triage, and feed/order confirmation flows — see `docs/DESIGN.md` §13 for the
  design of each.

## Documentation

- `docs/DESIGN.md` — architecture, tool contract rules, safety rules, and what's built vs planned.
- `docs/SOURCES.md` — provenance for every number CluckTalk uses.
- `docs/VERSIONS.md` — pinned/verified tool and package versions.
- `docs/AWS_SETUP.md` — live-mode AWS setup (not needed for the demo).
- `FRICTION_LOG.md` / `FEATURE_REQUESTS.md` — developer friction with the platforms used, recorded as it happens.
- `docs/TELUGU_REVIEW.md` — every Telugu string with its English pair and native-speaker review status.

## License

MIT. See `LICENSE`.
