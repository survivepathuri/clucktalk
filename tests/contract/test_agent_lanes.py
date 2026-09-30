"""A slow Daily Briefing job must never hold up a health check (Rule 11 review 2026-09-30, M4).

Both agents share one background runner. The briefing job can wait on the model for as long as a Bedrock call takes
(twice, with a retry); a farmer's health check queued behind it would sit "analyzing" and could pass its 2-minute
timeout. Real server, real ``ThreadRunner``, a briefing model call that blocks until the test lets it go."""

from __future__ import annotations

import threading
import time

from clucktalk.agents import AiServices
from clucktalk.agents.budget import AiBudget
from clucktalk.agents.model import ModelReply, ModelRequest
from clucktalk.agents.runner import ThreadRunner
from clucktalk.server.farm_state import DemoFarmSource
from tests.contract.conftest import FIXED_DAY, Clock, _start
from tests.contract.test_health_tools import Rig
from tests.fakes import ALWAYS_ROUTINE, _rankable_ids


class BlockingBriefingModel:
    """Answers health checks at once; a briefing call blocks until ``release`` is set."""

    engine = "scripted"
    model_id = "scripted-test-model"

    def __init__(self) -> None:
        self.briefing_started = threading.Event()
        self.release = threading.Event()

    def invoke(self, request: ModelRequest) -> ModelReply:
        ids = _rankable_ids(request)
        if ids is None:
            return ModelReply(
                ALWAYS_ROUTINE, self.engine, self.model_id, input_tokens=10, output_tokens=5, latency_ms=1
            )
        self.briefing_started.set()
        assert self.release.wait(30), "the test never released the briefing call"
        return ModelReply({"order": ids}, self.engine, self.model_id, input_tokens=10, output_tokens=5, latency_ms=1)


def test_a_briefing_job_waiting_on_the_model_does_not_hold_up_a_health_check():
    clock = Clock()
    source = DemoFarmSource(clock=lambda: FIXED_DAY, now=clock)
    model = BlockingBriefingModel()
    budget = AiBudget(source.store, clock, max_calls_per_day=100, min_interval_s=0)
    srv, stop = _start({}, source=source, ai=AiServices(model=model, budget=budget, runner=ThreadRunner()))
    try:
        sid, _ = srv.initialize()
        rig = Rig(srv, source, None, model, sid)  # type: ignore[arg-type]
        rig.call("get_daily_briefing")  # queues the briefing job
        assert model.briefing_started.wait(10), "the briefing job never reached the model"
        started = rig.call("start_health_check", house="shed 2", signs=["coughing"])["structuredContent"]
        assert started["status"] == "analyzing"
        deadline = time.monotonic() + 5
        status = "analyzing"
        while status == "analyzing" and time.monotonic() < deadline:
            time.sleep(0.05)
            status = rig.call("get_health_check", check_id=started["check_id"])["structuredContent"]["status"]
        assert status == "ready", "the health check was left waiting behind the briefing job"
    finally:
        model.release.set()
        stop()
