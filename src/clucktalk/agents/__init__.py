"""The agent layer (docs/DESIGN.md §18): slow-path jobs that ask a model for closed-list decisions.

``AiServices`` bundles what an agent needs: the model engine, the live-call budget (live mode only) and the job
runner. ``demo_ai`` (MOCK_BEDROCK=true, the default) makes no model calls; ``live_ai`` uses Amazon Nova via
Bedrock with the daily cap and throttle (clucktalk.agents.budget).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from clucktalk.agents.budget import AiBudget
from clucktalk.agents.model import ModelClient, RulesModel
from clucktalk.agents.runner import JobRunner, ThreadRunner
from clucktalk.config import Settings, require_live_ai
from clucktalk.store import Store


@dataclass
class AiServices:
    model: ModelClient
    budget: AiBudget | None  # None: demo rules, no live calls to count
    runner: JobRunner


def demo_ai() -> AiServices:
    return AiServices(model=RulesModel(), budget=None, runner=ThreadRunner())


def live_ai(settings: Settings, store: Store, now: Callable[[], datetime]) -> AiServices:
    """Raises ConfigError unless live AI was chosen explicitly with a model ID and a Region."""
    require_live_ai(settings)
    import boto3  # live mode only: demo mode never needs AWS

    from clucktalk.agents.bedrock import NovaModel

    assert settings.bedrock_model_id is not None and settings.aws_region is not None
    from botocore.config import Config

    # One HTTP attempt per model call (the ledger and throttle count real calls) and short timeouts, so a
    # check never sits "analyzing" for minutes (Rule 11 review 2026-09-29).
    config = Config(retries={"total_max_attempts": 1, "mode": "standard"}, connect_timeout=5, read_timeout=15)
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region, config=config)
    budget = AiBudget(store, now, max_calls_per_day=settings.ai_max_calls_per_day)
    return AiServices(model=NovaModel(client, settings.bedrock_model_id), budget=budget, runner=ThreadRunner())
