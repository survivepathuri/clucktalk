"""The eval runner's test-only hooks (scripts/eval_fast.py): the demo clock a step may move, ``say`` through the host
rules, ``answer_word``, ``expect_error``. A typo in a case must fail loudly, never be ignored."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("eval_fast_under_test", ROOT / "scripts" / "eval_fast.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)  # type: ignore[union-attr]


def test_a_step_with_say_uses_the_host_rules_to_pick_tool_and_arguments():
    tool, args, problem = ev._plan_step({"say": "kotam one is better now", "tool": "report_health_follow_up"}, {})
    assert (tool, problem) == ("report_health_follow_up", "")
    assert args == {"house": "kotam 1", "outcome": "better"}


def test_say_that_picks_another_tool_than_the_case_expects_is_a_problem():
    _, _, problem = ev._plan_step({"say": "kotam one is better now", "tool": "get_farm_status"}, {})
    assert "report_health_follow_up" in problem


def test_say_that_matches_nothing_is_a_problem():
    assert "nothing matched" in ev._plan_step({"say": "blah blah"}, {})[2]


@pytest.mark.parametrize(("word", "answer"), [("haan", "yes"), ("avunu", "yes"), ("nahi", "no"), ("vaddu", "no")])
def test_answer_words_become_yes_or_no(word, answer):
    _, args, problem = ev._plan_step({"tool": "t", "args": {"x": 1}, "answer_word": word}, {})
    assert problem == "" and args == {"x": 1, "answer": answer}


def test_an_answer_word_that_is_neither_is_a_problem():
    assert "not a yes or a no" in ev._plan_step({"tool": "t", "answer_word": "maybe"}, {})[2]


def test_saved_values_still_resolve_in_args():
    assert ev._plan_step({"tool": "t", "args": {"id": "$a"}}, {"a": "x"})[1] == {"id": "x"}


def test_a_misspelled_step_key_fails_the_case_instead_of_being_ignored():
    case = {"id": "x", "steps": [{"tool": "get_help", "demo_day_later": 3, "checks": []}]}
    ok, detail = ev._check_case(None, "", {}, case, ev.DemoClock(0))
    assert ok is False and "demo_day_later" in detail
