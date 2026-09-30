"""Daily Briefing agent (docs/DESIGN.md §18): the slow path that asks a model to order the non-health items.
The tool never waits for it: ``view`` answers at once and queues at most one job per (day, facts, minute)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pytest

from clucktalk.agents import AiServices
from clucktalk.agents.briefing import (
    AGENT,
    DAILY_CALLS,
    DEBOUNCE,
    MAX_TOKENS,
    TOOL_NAME,
    BriefingRanker,
    build_prompt,
)
from clucktalk.agents.budget import AiBudget
from clucktalk.agents.model import ModelError, RulesModel
from clucktalk.agents.runner import ManualRunner
from clucktalk.domain.briefing import Category, Fact
from clucktalk.domain.status import Level
from clucktalk.server.farm_state import IST
from clucktalk.store.sqlite import SqliteStore
from tests.fakes import ScriptedModel

DAY = date(2026, 9, 29)
FARM = "farm-test"


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 9, 29, 10, 0, tzinfo=IST)

    def __call__(self) -> datetime:
        return self.t


def _fact(fid: str, cat: Category, level: Level, *, pinned=False, number=1, values=None) -> Fact:
    return Fact(
        fact_id=fid,
        category=cat,
        level=level,
        severity=int(level),
        pinned=pinned,
        house_id=f"house-{number}",
        number=number,
        values=values or {},
    )


FACTS = [
    _fact("mortality_spike:house-2", Category.MORTALITY_SPIKE, Level.ALERT, pinned=True, number=2),
    _fact("feed_stock_low:house-2", Category.FEED_STOCK_LOW, Level.WATCH, number=2, values={"days_covered": 2}),
    _fact("weight_below_target:house-1", Category.WEIGHT_BELOW_TARGET, Level.WATCH, values={"pct_of_target": 85}),
    _fact("records_stale:house-3", Category.RECORDS_STALE, Level.WATCH, number=3, values={"days_since_record": 3}),
]
RANKABLE = ["feed_stock_low:house-2", "weight_below_target:house-1", "records_stale:house-3"]


class Rig:
    def __init__(self, model, *, max_calls: int = 100) -> None:
        self.clock = Clock()
        self.store = SqliteStore()
        self.runner = ManualRunner()
        budget = None if isinstance(model, RulesModel) else AiBudget(self.store, self.clock, max_calls, 0)
        self.ai = AiServices(model=model, budget=budget, runner=self.runner)
        self.model = model
        self.ranker = BriefingRanker(self.store, self.ai, self.clock)

    def view(self, facts=None):
        return self.ranker.view(FARM, DAY, FACTS if facts is None else facts)

    def ledger(self):
        return self.store.ai_calls(self.clock().date())


def test_demo_rules_never_queue_a_job_or_call_a_model():
    rig = Rig(RulesModel())
    v = rig.view()
    assert (v.order, v.engine, v.note) == ((), "rules", None)
    assert rig.runner.pending == 0


def test_the_first_answer_is_the_rules_order_and_says_the_ai_is_still_working():
    model = ScriptedModel({"order": list(reversed(RANKABLE))})
    rig = Rig(model)
    v = rig.view()
    assert (v.order, v.engine, v.note) == ((), "rules", "in_progress")
    assert rig.runner.pending == 1 and model.requests == []  # nothing waits for the model


def test_repeat_calls_within_a_minute_do_not_queue_duplicates():
    rig = Rig(ScriptedModel({"order": RANKABLE}))
    rig.view()
    rig.view()
    rig.view()
    assert rig.runner.pending == 1
    rig.clock.t += DEBOUNCE - timedelta(seconds=1)
    rig.view()
    assert rig.runner.pending == 1


def test_a_finished_ranking_is_served_and_not_recomputed():
    model = ScriptedModel({"order": list(reversed(RANKABLE))})
    rig = Rig(model)
    rig.view()
    assert rig.runner.run_all() == 1
    v = rig.view()
    assert v.order == tuple(reversed(RANKABLE)) and v.engine == "scripted" and v.note is None
    assert v.model_id == "scripted-test-model"
    assert rig.runner.pending == 0 and len(model.requests) == 1
    assert [(r["agent"], r["outcome"], r["input_tokens"], r["output_tokens"]) for r in rig.ledger()] == [
        (AGENT, "ok", 100, 20)
    ]


def test_the_request_is_a_forced_closed_list_call_with_no_pinned_id_and_no_free_text():
    model = ScriptedModel({"order": RANKABLE})
    rig = Rig(model)
    rig.view()
    rig.runner.run_all()
    req = model.requests[0]
    assert (req.agent, req.tool_name, req.max_tokens) == (AGENT, TOOL_NAME, MAX_TOKENS)
    assert req.schema["properties"]["order"]["items"]["enum"] == RANKABLE  # the pinned health fact is not on it
    assert "mortality_spike" not in req.user_text  # health is fixed by code; the model never sees or moves it
    assert req.rules_reply() == {"order": RANKABLE}
    for line in req.user_text.splitlines():
        assert re.fullmatch(r"- [a-z_]+:(?:house-\d+|farm): [a-z_]+, [a-z]+.*", line) or line.endswith(":"), line
    assert "farmer" not in req.system.lower().replace("a poultry farmer", "")  # no farmer-text channel exists
    assert "medicine" in req.system and "dose" in req.system  # the standing no-treatment instruction


def test_a_changed_farm_makes_the_stored_ranking_stale_and_queues_a_new_one():
    rig = Rig(ScriptedModel({"order": RANKABLE}, {"order": RANKABLE}))
    rig.view()
    rig.runner.run_all()
    changed = [*FACTS[:1], *(_fact("x:house-1", Category.FEED_STOCK_LOW, Level.WATCH), *FACTS[1:])]
    v = rig.view(changed)
    assert (v.order, v.note) == ((), "in_progress") and rig.runner.pending == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"order": ["mortality_spike:house-2"]},  # a pinned id is not on the list
        {"order": ["nope:house-1"]},
        {"order": [RANKABLE[0], RANKABLE[0]]},
        {"order": RANKABLE, "reason": "because"},
        "not even an object",
    ],
)
def test_an_invalid_reply_is_retried_once_then_fails_loud_with_the_rules_order(bad):
    model = ScriptedModel(bad, bad)
    rig = Rig(model)
    rig.view()
    rig.runner.run_all()
    assert len(model.requests) == 2  # one call and one retry, never more
    assert [r["outcome"] for r in rig.ledger()] == ["invalid_reply", "invalid_reply"]
    v = rig.view()
    assert (v.order, v.engine, v.note) == ((), "rules", "no_answer")
    assert rig.runner.pending == 0  # not retried until a minute has passed


def test_a_failed_ranking_is_tried_again_after_a_minute():
    rig = Rig(ScriptedModel(ModelError("down"), ModelError("down"), {"order": RANKABLE}))
    rig.view()
    rig.runner.run_all()
    assert [r["outcome"] for r in rig.ledger()] == ["error", "error"]
    assert rig.view().note == "no_answer"
    rig.clock.t += DEBOUNCE
    assert rig.view().note == "in_progress" and rig.runner.pending == 1  # a retry is running now
    rig.runner.run_all()
    v = rig.view()
    assert v.order == tuple(RANKABLE) and v.note is None


def test_a_reply_that_is_valid_on_the_retry_is_used():
    model = ScriptedModel({"order": ["nope"]}, {"order": [RANKABLE[1]]})
    rig = Rig(model)
    rig.view()
    rig.runner.run_all()
    assert [r["outcome"] for r in rig.ledger()] == ["invalid_reply", "ok"]
    assert rig.view().order == (RANKABLE[1],)


def test_the_daily_limit_answers_with_the_rules_order_and_says_so():
    model = ScriptedModel({"order": RANKABLE})
    rig = Rig(model, max_calls=0)
    rig.view()
    rig.runner.run_all()
    assert model.requests == []
    v = rig.view()
    assert (v.order, v.engine, v.note) == ((), "rules", "daily_limit")
    assert rig.runner.pending == 0  # remembered: no retry storm while the limit holds


def test_the_per_agent_cap_is_two_calls_a_run_and_eight_runs_a_day():
    assert DAILY_CALLS == 16 and MAX_TOKENS == 400


def test_with_nothing_to_rank_no_model_is_asked():
    model = ScriptedModel()
    rig = Rig(model)
    only_one = [FACTS[0], FACTS[1]]  # one pinned + one unpinned: nothing to put in order
    v = rig.view(only_one)
    assert (v.order, v.engine, v.note) == ((), "none", "not_needed")
    assert rig.runner.pending == 0 and model.requests == []


def test_the_prompt_lists_only_ids_categories_levels_and_numbers():
    text = build_prompt([f for f in FACTS if not f.pinned])
    assert "feed_stock_low:house-2: feed_stock_low, watch, days_covered=2" in text
    assert "weight_below_target:house-1: weight_below_target, watch, pct_of_target=85" in text


def _corrupt(rig, fp, text="not json"):
    rig.store._db.execute(
        "INSERT OR REPLACE INTO briefing_ranks VALUES (?, ?, ?, ?, ?, ?, ?)",
        (FARM, DAY.isoformat(), fp, text, "nova", None, None),
    )


def test_an_unreadable_stored_ranking_is_logged_said_and_prepared_again(caplog):
    """H2 (Rule 11 review 2026-09-30): never a crash; the rules order, labelled; the ranking is rebuilt."""
    from clucktalk.domain.briefing import fingerprint

    rig = Rig(ScriptedModel({"order": list(reversed(RANKABLE))}))
    _corrupt(rig, fingerprint(FACTS))
    v = rig.view()
    assert (v.order, v.engine, v.note) == ((), "rules", "unreadable")
    assert rig.runner.pending == 1 and "unreadable" in caplog.text
    assert rig.view().note == "unreadable" and rig.runner.pending == 1  # debounced like any other job
    rig.runner.run_all()
    v = rig.view()
    assert v.order == tuple(reversed(RANKABLE)) and v.note is None  # the row was replaced by a good one


def test_an_unreadable_ranking_for_other_facts_is_simply_stale():
    rig = Rig(ScriptedModel({"order": RANKABLE}))
    _corrupt(rig, "0" * 16)
    assert rig.view().note == "in_progress"
