"""Test and eval doubles for the agent layer: scripted model replies and failures, so the safety floor, the
retry and the fail-loud paths can be exercised without AWS (docs/DESIGN.md §18)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clucktalk.agents.model import ModelError, ModelReply, ModelRequest


class ScriptedModel:
    """Returns the scripted replies in order (a callable reply is called with the request); an Exception
    instance is raised instead. Every request is kept, so tests can read the exact prompt."""

    engine = "scripted"
    model_id = "scripted-test-model"

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.requests: list[ModelRequest] = []

    def invoke(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("ScriptedModel called more times than scripted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        data = reply(request) if callable(reply) else reply
        return ModelReply(data, self.engine, self.model_id, input_tokens=100, output_tokens=20, latency_ms=5)


class RepeatingModel(ScriptedModel):
    """Gives the same reply to every request (eval fixtures run many cases against one server)."""

    def __init__(self, reply: Any) -> None:
        super().__init__()
        self._reply = reply

    def invoke(self, request: ModelRequest) -> ModelReply:
        self.replies = [self._reply]
        return super().invoke(request)


ALWAYS_ROUTINE: dict[str, Any] = {"urgency": "routine", "consistent_with": [], "checks": []}


def always_routine() -> RepeatingModel:
    """A model that tries to call everything routine: the floor must hold."""
    return RepeatingModel(ALWAYS_ROUTINE)


def always_fails() -> RepeatingModel:
    """A model whose every call fails: results must say so, never invent a triage."""
    return RepeatingModel(ModelError("simulated Bedrock outage (test fixture)"))


FIXTURES: dict[str, Callable[[], ScriptedModel]] = {"always_routine": always_routine, "always_fails": always_fails}
