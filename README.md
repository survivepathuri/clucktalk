# CluckTalk (కోడి మిత్ర)

The voice farm manager for India's **broiler** poultry farmers. A self-hosted MCP server (spec 2025-11-25,
Streamable HTTP) plus an Agent Skill, built for the Alexa+ add-on program.

> **Status**: in development. Nothing below is claimed working unless it has evidence in `docs/evidence/` or a
> passing check in `python tasks.py check` / `python tasks.py eval-fast`. See `docs/DESIGN.md` for the full design
> and what is built vs planned, and `docs/EVALS.md` for the current golden-suite score.

## Quick start (Windows, venv only — Docker is optional and never required)

```
git clone <this repo>
cd CluckTalk
python tasks.py setup    :: creates .venv (Python 3.13) and installs pinned dependencies
python tasks.py run      :: starts the MCP server + the Alexa+ Simulator, opens http://127.0.0.1:8766/
```

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
- **What can you do?** (`get_help`).
- A local **Alexa+ Simulator** (Echo Show / Echo Dot device modes, voice and text, a developer panel showing the
  exact MCP wire).

## Roadmap

- **Layer farming.** The domain layer already models egg-laying flocks (status, feed planning), but the current
  build, demo data and video target **broiler** farms only. Extending the voice/card experience to layer flocks
  the way broilers are covered today is future work.
- Voice record book, the full Contract Earnings Tracker (sensitivity/what-if), vaccination planner and vaccine-day
  coach, health triage, daily briefing, and feed/order confirmation flows — see `docs/DESIGN.md` §13 for the
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
