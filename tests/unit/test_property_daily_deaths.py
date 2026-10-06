"""Step 51 part B: the farmer's own daily deaths rule can only RAISE a level, never lower one, and never changes the vet
advice. Hypothesis builds random sequences of health checks, death records and clock moves on the demo farm, plus random
rules. After every event the farm status (whole farm and each shed) and the daily briefing are built with the rule OFF,
then ON, then OFF again. With the rule on: every level is >= the level without it; safety.level is >= and
vet_contact_advised and every non-rule finding are exactly equal; reason codes only gain the rule's own code; every
item and finding without the rule is still there, unchanged; the text only gains his sentence and his note; and
with the rule off again the answers are exactly the first ones."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from clucktalk.agents import demo_ai
from clucktalk.agents.briefing import BriefingRanker
from clucktalk.domain.daily_deaths import DailyDeathsRule
from clucktalk.domain.models import DailyRecord
from clucktalk.domain.triage import Urgency
from clucktalk.server.daily_deaths import RuleState
from clucktalk.server.tools.briefing import build_briefing
from clucktalk.server.tools.farm_status import build_status
from tests.unit.test_property_follow_up_sequences import World

PROPERTY = settings(
    max_examples=30, derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow], database=None
)
RANK = {"ok": 0, "unknown": 1, "info": 0, "none": 0, "watch": 1, "alert": 2}
SAFETY_RANK = {"OK": 0, "UNKNOWN": 1, "WATCH": 1, "ALERT": 2}
RULE_CODE = "daily_deaths_rule"

events = st.one_of(
    st.tuples(st.just("check"), st.integers(1, 3), st.sampled_from(list(Urgency))),
    st.tuples(st.just("record"), st.integers(1, 3), st.tuples(st.integers(0, 2), st.sampled_from([0, 1, 5, 60, 400]))),
    st.tuples(st.just("clock"), st.just(0), st.integers(0, 4)),
)
rules = st.builds(
    DailyDeathsRule,
    st.decimals(0, 60, allow_nan=False, places=2),
    st.one_of(st.none(), st.text(max_size=30)),
    st.booleans(),
)


class Fixed:
    def __init__(self, rule, unreadable=False):
        self.state = RuleState(rule, unreadable)

    def current(self):
        return self.state


def snapshot(world, ranker):
    status = build_status(world.source, None).model_dump(mode="json")
    sheds = [build_status(world.source, f"shed {n}").model_dump(mode="json") for n in (1, 2, 3)]
    brief = build_briefing(world.source, ranker, False).model_dump(mode="json")
    return status, sheds, brief


def apply(world, event):
    kind, house, arg = event
    if kind == "check":
        world.add_check(house, arg)
    elif kind == "record":
        days_ago, deaths = arg
        day = world.clock.today() - timedelta(days=days_ago)
        world.store.put_record(world.source.farm_id, f"house-{house}", DailyRecord(day, deaths, 100.0))
    else:
        world.clock.set_days_later(min(30, world.clock.days_later + arg))


def findings_without_rule(answer):
    return [[f for f in h["findings"] if f["code"] != RULE_CODE] for h in answer["houses"]]


def check_pair(on, off):
    assert RANK[on["level"]] >= RANK[off["level"]]  # never lower
    assert SAFETY_RANK[on["safety"]["level"]] >= SAFETY_RANK[off["safety"]["level"]]
    assert on["safety"]["vet_contact_advised"] == off["safety"]["vet_contact_advised"]  # the vet advice is untouched
    gained = set(on["safety"]["reason_codes"]) - set(off["safety"]["reason_codes"])
    assert gained <= {RULE_CODE} and set(off["safety"]["reason_codes"]) <= set(on["safety"]["reason_codes"])
    if "houses" in on:
        assert findings_without_rule(on) == findings_without_rule(off)  # every other finding is exactly as before
        for hon, hoff in zip(on["houses"], off["houses"], strict=True):
            assert RANK[hon["level"]] >= RANK[hoff["level"]]
            if not any(f["code"] == RULE_CODE for f in hon["findings"]):
                assert hon == hoff  # a shed the rule did not fire on is untouched, field for field
            else:
                assert hon["level"] in ("watch", "alert")
    else:
        off_items = {i["fact_id"]: i for i in off["items"]}
        on_items = {i["fact_id"]: i for i in on["items"]}
        for fid, item in on_items.items():
            if item["category"] != RULE_CODE and fid in off_items:
                assert item["level"] == off_items[fid]["level"]
        assert all(i["level"] == "watch" for i in on["items"] if i["category"] == RULE_CODE)


@PROPERTY
@given(st.lists(events, max_size=5), rules)
def test_the_deaths_rule_never_lowers_a_level_and_never_changes_the_vet_advice(sequence, rule):
    world = World()
    ranker = BriefingRanker(world.source.store, demo_ai(), world.source.now)
    for event in [None, *sequence]:
        if event is not None:
            apply(world, event)
        world.source.deaths_rule = None
        off = snapshot(world, ranker)
        world.source.deaths_rule = Fixed(rule)
        on = snapshot(world, ranker)
        world.source.deaths_rule = None
        off_again = snapshot(world, ranker)
        assert off == off_again  # off again: exactly the first answers
        check_pair(on[0], off[0])
        check_pair(on[2], off[2])
        for a, b in zip(on[1], off[1], strict=True):
            check_pair(a, b)
        if not rule.note or not rule.note.strip():
            assert "Your note:" not in on[0]["text_en"].replace(off[0]["text_en"], "")
        world.source.deaths_rule = Fixed(None, unreadable=True)  # unreadable: said, and nothing else moves
        bad = snapshot(world, ranker)
        for a, b in zip((bad[0], bad[2]), (off[0], off[2]), strict=True):
            assert a["level"] == b["level"] and a["safety"] == b["safety"]
        world.source.deaths_rule = None


def test_the_property_really_fires_the_rule_on_the_demo_farm():
    """Guard against a property that never exercises the rule: shed 2 lost 26 of 4000 birds today (6.5 per 1000)."""
    world = World()
    ranker = BriefingRanker(world.source.store, demo_ai(), world.source.now)
    world.source.deaths_rule = Fixed(DailyDeathsRule(Decimal("1"), "n", False))
    status, sheds, brief = snapshot(world, ranker)
    assert any(f["code"] == RULE_CODE for f in sheds[1]["houses"][0]["findings"])
    assert any(i["category"] == RULE_CODE for i in brief["items"] + [])
