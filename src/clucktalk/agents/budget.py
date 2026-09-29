"""Live model spend limits (user decision 2026-09-29; docs/DESIGN.md §18).

- A daily cap on live calls (hard cap ``HARD_DAILY_CAP``; a lower one may be configured), plus a per-agent cap,
  both counted from the store's call ledger, so a restart never resets them. Failed calls count too.
- A throttle: at least ``min_interval_s`` between live calls (the account's applied Nova 2 Lite quota is 20
  requests/minute, docs/AWS_SETUP.md §5.1; 4 s keeps us at 15/minute or less).
Demo mode (``RulesModel``) has no budget: it makes no model calls.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime

from clucktalk.config import AI_HARD_DAILY_CAP
from clucktalk.store import Store

HARD_DAILY_CAP = AI_HARD_DAILY_CAP
DEFAULT_MIN_INTERVAL_S = 4.0


class AiBudget:
    def __init__(
        self,
        store: Store,
        now: Callable[[], datetime],
        max_calls_per_day: int = HARD_DAILY_CAP,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 <= max_calls_per_day <= HARD_DAILY_CAP:
            raise ValueError(f"max_calls_per_day must be 0-{HARD_DAILY_CAP} (hard cap)")
        self.store = store
        self.now = now
        self.max_calls_per_day = max_calls_per_day
        self.min_interval_s = min_interval_s
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._last: float | None = None

    def acquire(self, agent: str, agent_daily_cap: int) -> bool:
        """True if one more live call may be made now (after waiting out the throttle); False if a cap is reached.
        The caller must ``record`` every call it then makes."""
        with self._lock:
            day = self.now().date()
            if self.store.count_ai_calls(day) >= self.max_calls_per_day:
                return False
            if self.store.count_ai_calls(day, agent) >= agent_daily_cap:
                return False
            if self._last is not None:
                wait = self.min_interval_s - (self._monotonic() - self._last)
                if wait > 0:
                    self._sleep(wait)
            self._last = self._monotonic()
            return True

    def record(
        self,
        agent: str,
        engine: str,
        model_id: str | None,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        outcome: str,
    ) -> None:
        self.store.add_ai_call(self.now(), agent, engine, model_id, input_tokens, output_tokens, latency_ms, outcome)
