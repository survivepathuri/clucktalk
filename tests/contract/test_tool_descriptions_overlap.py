"""Review finding M8 (Step 47C): "how is my farm" and "what needs attention today" no longer fit both tools. The two
descriptions say what each is for and name the other tool for the other job (wording only; tool names unchanged)."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from tests.contract.test_health_tools import _rig


@pytest.fixture
def tools():
    for rig in _rig(RulesModel()):
        yield {t["name"]: t for t in rig.live.call(rig.sid, "tools/list")["result"]["tools"]}


def test_the_tool_names_are_unchanged(tools):
    assert {"get_farm_status", "get_daily_briefing", "start_health_check"} <= set(tools)


def test_the_status_description_says_what_it_is_for_and_sends_the_other_jobs_away(tools):
    text = tools["get_farm_status"]["description"]
    assert "right now" in text and "open health check" in text and "follow-up" in text
    assert "get_daily_briefing" in text and "start_health_check" in text
    assert "Not for" in text


def test_the_briefing_description_says_what_it_is_for_and_sends_the_other_jobs_away(tools):
    text = tools["get_daily_briefing"]["description"]
    assert "ranked" in text and "whole farm" in text and "what to do first today" in text
    assert "get_farm_status" in text and "Not for" in text
    assert "Never gives a medicine or dose" in text  # the existing safety sentence stays


def test_the_two_descriptions_no_longer_claim_the_same_question(tools):
    status, briefing = tools["get_farm_status"]["description"], tools["get_daily_briefing"]["description"]
    assert "needs attention on the farm today" not in status
    assert "how a house" not in briefing and "is doing" not in briefing.split("Not for")[0]
    # each one names the other tool exactly once, as the place for the other job
    assert status.count("get_daily_briefing") == 1 and briefing.count("get_farm_status") == 1
