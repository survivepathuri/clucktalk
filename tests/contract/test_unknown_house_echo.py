"""Review finding L2 (Step 47C), over real HTTP: an unknown house name comes back cleaned and shortened in the spoken
error, in both languages, for every tool that takes a house."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from tests.contract.test_health_tools import _rig

NASTY = "x" * 300 + "🐔<script>alert(1)</script>\n\x00"
TOOLS = [
    ("get_farm_status", {}),
    ("plan_feed", {}),
    ("plan_sale", {}),
    ("start_health_check", {"signs": ["coughing"]}),
    ("report_health_follow_up", {"outcome": "better"}),
    ("log_daily_record", {"deaths": 1}),
]


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


@pytest.mark.parametrize(("tool", "extra"), TOOLS)
def test_an_unknown_house_is_not_echoed_raw(rig, tool, extra):
    result = rig.call(tool, house=NASTY, **extra)
    assert result.get("isError") is True, (tool, result)
    meta = result["_meta"]["clucktalk/error"]
    spoken = " ".join([result["content"][0]["text"], *meta.values()]) if isinstance(meta, dict) else str(result)
    for bad in ("🐔", "<script>", "\n", "\x00", "x" * 30):
        assert bad not in spoken, (tool, bad)
    assert "House 1, House 2, House 3" in meta["next_step_en"]
