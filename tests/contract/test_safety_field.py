"""Review finding M6, stage 1 (Step 47C), over real HTTP: every successful briefing and farm-status response carries
`safety` {level, reason_codes, vet_contact_advised}; the level always equals the card's own level and is never lower
than the rules that set it; the briefing and the status agree for the same shed in every urgency and follow-up state;
the schema is declared in tools/list."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.triage import Urgency
from clucktalk.server.tools.briefing import ItemOut, _needs_safety_step
from tests.contract.test_follow_up_surfaces import _brief, _handoff, _status
from tests.contract.test_follow_up_tools import _ask_and_answer, _stored_check
from tests.contract.test_health_tools import _rig

CARD = {"ok": "OK", "info": "OK", "none": "OK", "watch": "WATCH", "alert": "ALERT", "unknown": "UNKNOWN"}
RANK = {"OK": 0, "WATCH": 1, "ALERT": 2, "UNKNOWN": 3}
FIELDS = {"level", "reason_codes", "vet_contact_advised"}


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _house1_items(brief: dict) -> list[dict]:
    return [i for i in brief["items"] if i["house_id"] == "house-1"]


def _house1_card_level(brief: dict) -> str:
    levels = [CARD[i["level"]] for i in _house1_items(brief)]
    return max(levels, key=RANK.__getitem__, default="OK")


def _house1_vet(brief: dict) -> bool:
    """The briefing's own closing-step rule for this shed's items, or an escalated follow-up (its sentence says so)."""
    return any(
        _needs_safety_step(ItemOut(**i)) or (i["category"] == "follow_up" and i["values"].get("state") == "escalated")
        for i in _house1_items(brief)
    )


def _check_one_state(rig) -> None:
    brief, one, farm = _brief(rig), _status(rig, house="shed 1"), _status(rig)
    for sc in (brief, one, farm):
        assert set(sc["safety"]) == FIELDS and isinstance(sc["safety"]["reason_codes"], list)
    # the level always equals the card's own level
    assert brief["safety"]["level"] == CARD[brief["level"]]
    assert one["safety"]["level"] == CARD[one["level"]] == CARD[one["houses"][0]["level"]]
    assert farm["safety"]["level"] == CARD[farm["level"]]
    # the briefing and the status agree for the same shed
    assert one["safety"]["level"] == _house1_card_level(brief)
    # the farm-wide level is never lower than any shed's
    house_levels = [CARD[h["level"]] for h in farm["houses"]]
    assert RANK[farm["safety"]["level"]] >= max(RANK[h] for h in house_levels)
    # a level above OK always says why
    for sc in (brief, one, farm):
        if sc["safety"]["level"] in ("WATCH", "ALERT"):
            assert sc["safety"]["reason_codes"], sc["safety"]
    # the vet flag: on whenever the briefing says the vet line for this shed, and the same in the status
    assert one["safety"]["vet_contact_advised"] == _house1_vet(brief)
    if _house1_vet(brief):
        assert brief["safety"]["vet_contact_advised"] is True and farm["safety"]["vet_contact_advised"] is True


@pytest.mark.parametrize("days_ago", [0, 1, 2, 3, 5, 9, 12, 30])
@pytest.mark.parametrize("urgency", list(Urgency))
def test_safety_agrees_for_every_urgency_and_day(rig, urgency, days_ago):
    _stored_check(rig, days_ago=days_ago, urgency=urgency)
    _check_one_state(rig)


@pytest.mark.parametrize("outcome", ["better", "same", "worse", "not_sure"])
@pytest.mark.parametrize("urgency", [Urgency.WATCH, Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT])
def test_safety_agrees_after_every_answer(rig, urgency, outcome):
    _stored_check(rig, days_ago=1 if urgency >= Urgency.URGENT else 3, urgency=urgency)
    _ask_and_answer(rig, outcome)
    _check_one_state(rig)


def test_safety_agrees_after_a_vet_handoff(rig):
    _stored_check(rig, days_ago=1, urgency=Urgency.URGENT)
    _handoff(rig)
    _check_one_state(rig)


def test_an_urgent_check_advises_the_vet_and_is_never_lower_than_alert(rig):
    _stored_check(rig, days_ago=1, urgency=Urgency.URGENT)
    one = _status(rig, house="shed 1")["safety"]
    assert one["level"] == "ALERT" and one["vet_contact_advised"] is True and one["reason_codes"]


def test_a_healthy_shed_is_ok_with_no_reasons_and_no_vet(rig):
    one = _status(rig, house="shed 1")["safety"]
    assert one == {"level": "OK", "reason_codes": [], "vet_contact_advised": False}


def test_it_is_present_on_every_briefing_page(rig):
    for more in (False, True):
        assert set(_brief(rig, more=more)["safety"]) == FIELDS


def test_the_schema_is_declared_in_tools_list(rig):
    tools = {t["name"]: t for t in rig.live.call(rig.sid, "tools/list")["result"]["tools"]}
    for name in ("get_daily_briefing", "get_farm_status"):
        schema = tools[name]["outputSchema"]
        assert "safety" in schema["properties"] and "safety" in schema["required"]
        defs = schema.get("$defs", {})
        safety = defs.get("SafetyOut") or schema["properties"]["safety"]
        assert set(safety["properties"]) == FIELDS and safety["additionalProperties"] is False
        assert safety["properties"]["level"]["enum"] == ["OK", "WATCH", "ALERT", "UNKNOWN"]
