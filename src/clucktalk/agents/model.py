"""The model interface every agent uses (docs/DESIGN.md §18).

An agent asks for one forced tool call whose input is a closed-list JSON object; code then validates it. Two
engines: ``RulesModel`` (demo mode, ``MOCK_BEDROCK=true``: the agent's own deterministic rules, no network,
labelled "AI: off") and ``clucktalk.agents.bedrock.NovaModel`` (live).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class ModelError(RuntimeError):
    """The model call failed (network, throttling, access, or no tool call). Logged; never spoken as-is."""


@dataclass(frozen=True)
class ModelRequest:
    agent: str
    system: str
    user_text: str  # farmer free text only ever inside a delimited data block (clucktalk.agents.triage)
    tool_name: str
    tool_description: str
    schema: dict[str, Any]  # JSON schema of the one tool call's input; closed lists only
    max_tokens: int
    rules_reply: Callable[[], Any]  # the demo rules' answer, in the same schema; used only by RulesModel


@dataclass(frozen=True)
class ModelReply:
    data: Any  # the tool call's input, unvalidated
    engine: str
    model_id: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int


class ModelClient(Protocol):
    engine: str
    model_id: str | None

    def invoke(self, request: ModelRequest) -> ModelReply: ...


class RulesModel:
    """Demo mode: answers with the agent's deterministic rules. Not AI, and always labelled so."""

    engine = "rules"
    model_id = None

    def invoke(self, request: ModelRequest) -> ModelReply:
        return ModelReply(request.rules_reply(), self.engine, None, 0, 0, 0)
