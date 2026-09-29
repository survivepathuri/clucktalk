"""Where agent jobs run: off the tool call, so every MCP tool returns within its latency budget (Rule 4).

``ThreadRunner`` (the server): one background worker thread, jobs in order. A job that raises is logged with its
traceback (never swallowed, Rule 6); the job itself is responsible for saving a "failed" state the farmer hears.
``ManualRunner`` (tests, evals): jobs wait until the test runs them, so the "still checking" state is observable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

logger = logging.getLogger("clucktalk.agents")

Job = Callable[[], None]


class JobRunner(Protocol):
    def submit(self, job: Job) -> None: ...


def _logged(job: Job) -> None:
    try:
        job()
    except Exception:  # noqa: BLE001 - a background job has no caller to raise to; logged with traceback
        logger.exception("agent job failed")


class ThreadRunner:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clucktalk-agent")

    def submit(self, job: Job) -> None:
        self._pool.submit(_logged, job)


class ManualRunner:
    def __init__(self) -> None:
        self._jobs: list[Job] = []

    def submit(self, job: Job) -> None:
        self._jobs.append(job)

    @property
    def pending(self) -> int:
        return len(self._jobs)

    def run_all(self) -> int:
        """Run every queued job (including jobs queued meanwhile); returns how many ran."""
        ran = 0
        while self._jobs:
            _logged(self._jobs.pop(0))
            ran += 1
        return ran
