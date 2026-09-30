"""Daily Briefing agent: the slow path behind ``get_daily_briefing`` (docs/DESIGN.md §3, §18).

The tool answers at once from code (facts + rules order). This agent may improve the order of the NON-health
facts: one forced call whose input is a single list of the offered ids (no free-text field), validated strictly,
one retry, then fail loud. Health facts are pinned by code and never offered to the model. Nothing here waits: the
tool calls ``view``, which reads a stored ranking or queues one job and answers with the rules order, labelled.
- No farmer text and no prose in the prompt: only fact ids, categories, levels and numbers from the record book.
- Two calls per run at most; a run at most once a minute per (day, facts); 16 calls a day for this agent.
- Daily cap reached: the rules order, labelled. Model failure: said plainly, never an invented order.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from clucktalk.agents.model import ModelError, ModelRequest
from clucktalk.domain.briefing import (
    BriefingRank,
    Fact,
    InvalidRanking,
    fingerprint,
    ranking_schema,
    validate_ranking,
)
from clucktalk.store import Store

if TYPE_CHECKING:
    from clucktalk.agents import AiServices

logger = logging.getLogger("clucktalk.agents")

AGENT = "briefing"
TOOL_NAME = "rank_briefing"
MAX_TOKENS = 400  # a reply is a short list of ids
CALLS_PER_RUN = 2  # one call + one retry
DAILY_RUNS = 8
DAILY_CALLS = CALLS_PER_RUN * DAILY_RUNS  # per-agent cap, inside the global daily cap
DEBOUNCE = timedelta(seconds=60)
LEVEL_WORD = {0: "info", 1: "watch", 2: "alert"}

SYSTEM_PROMPT = (
    "You order a poultry farmer's daily briefing in India. Each item is a fact from the farm's own records. "
    "Answer only by calling rank_briefing with `order`: the offered item ids, the ones that most need attention "
    "first. Health items are already fixed at the top by the system and are not offered. Put items that cost birds "
    "or money if left today (feed running out, weight or feed problems, a sale window) before reminders. "
    "Never suggest a medicine, drug, vaccine or dose."
)
TOOL_DESCRIPTION = "Report the order of the offered items using only the offered ids."
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class RankView:
    """What ``BriefingRanker.view`` tells the tool. ``order`` is empty when the rules order stands."""

    order: tuple[str, ...]
    engine: str  # "rules" | "none" | the model engine that ordered the facts
    model_id: str | None
    note: str | None  # None | "in_progress" | "no_answer" | "daily_limit" | "not_needed"


@dataclass
class _Attempt:
    at: datetime
    status: str  # "pending" | "failed"


def _value(v: object) -> str | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, str) and _ISO_DAY.fullmatch(v):
        return v
    return None  # lists and prose never reach the prompt


def build_prompt(rankable: Iterable[Fact]) -> str:
    lines = ["Items to put in order (most in need of attention first):"]
    for f in rankable:
        vals = [f"{k}={s}" for k, v in f.values.items() if (s := _value(v)) is not None]
        lines.append(f"- {f.fact_id}: {f.category.value}, {LEVEL_WORD[int(f.level)]}" + "".join(f", {x}" for x in vals))
    return "\n".join(lines)


class BriefingRanker:
    def __init__(self, store: Store, ai: AiServices, now: Callable[[], datetime]) -> None:
        self._store, self._ai, self._now = store, ai, now
        self._lock = threading.Lock()
        self._attempts: dict[tuple[str, date, str], _Attempt] = {}

    def view(self, farm_id: str, day: date, facts: tuple[Fact, ...]) -> RankView:
        """Never blocks and never calls a model. ``facts`` must be in rules order."""
        if self._ai.model.engine == "rules":
            return RankView((), "rules", None, None)  # demo mode: no model, no job
        if sum(1 for f in facts if not f.pinned) < 2:
            return RankView((), "none", None, "not_needed")  # nothing to put in order
        fp = fingerprint(facts)
        stored = self._store.get_briefing_rank(farm_id, day)
        if stored is not None and stored.fingerprint == fp:
            return RankView(stored.order, stored.engine, stored.model_id, stored.note)
        key = (farm_id, day, fp)
        with self._lock:
            now = self._now()
            attempt = self._attempts.get(key)
            if attempt is None or now - attempt.at >= DEBOUNCE:
                self._attempts = {k: v for k, v in self._attempts.items() if k[1] == day}
                attempt = self._attempts[key] = _Attempt(now, "pending")
                self._ai.runner.submit(lambda: self._job(key, facts))
            note = "in_progress" if attempt.status == "pending" else "no_answer"
        return RankView((), "rules", None, note)

    def _job(self, key: tuple[str, date, str], facts: tuple[Fact, ...]) -> None:
        try:
            done = self._rank(key, facts)
        except Exception:  # noqa: BLE001 - a background job: logged with its traceback, then marked failed
            logger.exception("briefing %s: unexpected error; the AI ordering is marked failed", key[1])
            done = False
        with self._lock:
            if done:
                self._attempts.pop(key, None)  # the stored ranking now answers
            elif key in self._attempts:
                self._attempts[key].status = "failed"

    def _rank(self, key: tuple[str, date, str], facts: tuple[Fact, ...]) -> bool:
        farm_id, day, fp = key
        stored = self._store.get_briefing_rank(farm_id, day)
        if stored is not None and stored.fingerprint == fp:
            return True
        rankable = [f for f in facts if not f.pinned]
        ids = [f.fact_id for f in rankable]
        allowed = frozenset(ids)
        request = ModelRequest(
            agent=AGENT,
            system=SYSTEM_PROMPT,
            user_text=build_prompt(rankable),
            tool_name=TOOL_NAME,
            tool_description=TOOL_DESCRIPTION,
            schema=ranking_schema(ids),
            max_tokens=MAX_TOKENS,
            rules_reply=lambda: {"order": ids},
        )
        budget = self._ai.budget
        for attempt in range(1, CALLS_PER_RUN + 1):
            if budget is not None and not budget.acquire(AGENT, DAILY_CALLS):
                logger.warning("briefing: daily AI limit reached; the rules order stands")
                self._store.save_briefing_rank(BriefingRank(farm_id, day, fp, (), "rules", None, "daily_limit"))
                return True
            t0 = time.perf_counter()
            try:
                reply = self._ai.model.invoke(request)
            except Exception as exc:  # noqa: BLE001 - every acquired call is ledgered before anything else happens
                if budget is not None:
                    elapsed = round((time.perf_counter() - t0) * 1000)
                    billed = exc if isinstance(exc, ModelError) else ModelError(str(exc))
                    latency = elapsed if billed.latency_ms is None else billed.latency_ms
                    budget.record(
                        AGENT, self._ai.model.engine, self._ai.model.model_id, billed.input_tokens,
                        billed.output_tokens, latency, "error",
                    )  # fmt: skip
                if not isinstance(exc, ModelError):
                    raise
                logger.warning("briefing: model call %d failed: %s", attempt, exc)
                continue
            order: tuple[str, ...] | None = None
            outcome = "invalid_reply"
            try:
                order = validate_ranking(reply.data, allowed)
                outcome = "ok"
            except InvalidRanking as exc:
                logger.warning("briefing: model reply %d rejected (%s)", attempt, exc)
            finally:  # the reply is ledgered whatever validation does
                if budget is not None:
                    budget.record(
                        AGENT, reply.engine, reply.model_id, reply.input_tokens, reply.output_tokens,
                        reply.latency_ms, outcome,
                    )  # fmt: skip
            if order is not None:
                self._store.save_briefing_rank(
                    BriefingRank(farm_id, day, fp, order, reply.engine, reply.model_id, None)
                )
                return True
        logger.error("briefing: no usable model reply; the rules order stands")
        return False
