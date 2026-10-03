"""Step 47C part E: no tool description claims real-time or live data, and a tool that returns simulated data says
SIMULATED in its description (CLAUDE.md: simulated data is always labelled). plan_sale says that its market price is
a simulated value, not a real market quote, that a rate the farmer states is used as given, and that the result says
so too."""

from __future__ import annotations

import re

import pytest

from clucktalk.agents.model import RulesModel
from tests.contract.test_health_tools import _rig

CLAIMS = re.compile(r"real[- ]?time|\blive (?:market|data|price|prices|rate|rates|feed|sensor|sensors|weather)\b", re.I)
# tools whose results contain simulated data: the market rate, the supplier's feed prices, the vet SMS
SIMULATED = ("plan_sale", "plan_feed", "prepare_vet_handoff")


@pytest.fixture(scope="module")
def tools():
    for rig in _rig(RulesModel()):
        yield {t["name"]: t for t in rig.live.call(rig.sid, "tools/list")["result"]["tools"]}


def _text(tool: dict) -> str:
    params = " ".join(p.get("description", "") for p in tool["inputSchema"].get("properties", {}).values())
    return f"{tool.get('title', '')} {tool.get('description', '')} {params}"


def test_every_tool_is_covered(tools):
    assert len(tools) == 14 and set(SIMULATED) <= set(tools)


def test_no_description_claims_real_time_or_live_data(tools):
    for name, tool in tools.items():
        assert not CLAIMS.search(_text(tool)), name


@pytest.mark.parametrize("name", SIMULATED)
def test_a_tool_with_simulated_data_says_simulated_in_its_description(tools, name):
    assert re.search(r"simulated", tools[name]["description"], re.I), name


def test_the_checker_itself_catches_a_claim():
    for bad in ("Real-time market prices", "uses live market data", "realtime sensors", "Live prices for the farm"):
        assert CLAIMS.search(bad), bad
    for fine in ("per kg live weight", "live-bird rate in rupees", "the live birds", "live weight"):
        assert not CLAIMS.search(fine), fine


def test_plan_sale_says_its_price_is_simulated_and_not_a_real_quote(tools):
    text = tools["plan_sale"]["description"]
    assert "simulated" in text and "not a real market quote" in text
    assert "live_price_per_kg" in text and "used as given" in text
    assert "result text says" in text


def test_the_plan_sale_result_does_say_simulated_when_it_uses_the_simulated_price(tools):
    for rig in _rig(RulesModel()):
        sc = rig.call("plan_sale", house="shed 3")["structuredContent"]
        assert sc["plans"][0]["price_is_simulated"] is True
        assert "Simulated" in sc["text_en"] or "simulated" in sc["text_en"]
        given = rig.call("plan_sale", house="shed 3", live_price_per_kg=95.0)["structuredContent"]
        assert given["plans"][0]["price_is_simulated"] is False
