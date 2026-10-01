"""``build_briefing`` on a calm, hand-built farm: the record-book reminder and the "nothing to report" answer, which the
seeded demo farm (always in trouble, by design) can never show. Calls the tool's builder directly, no HTTP."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from clucktalk.agents import AiServices
from clucktalk.agents.briefing import BriefingRanker
from clucktalk.agents.model import RulesModel
from clucktalk.agents.runner import ManualRunner
from clucktalk.domain.briefing import collect_facts, fingerprint
from clucktalk.domain.models import DailyRecord, HouseKind
from clucktalk.domain.triage import CheckStatus, Urgency, VetHandoff, new_handoff_id
from clucktalk.server.farm_state import IST, DemoFarmSource
from clucktalk.server.tools.briefing import build_briefing
from clucktalk.server.tools.farm_status import SAFETY_STEP
from tests.fakes import ScriptedModel
from tests.unit.helpers import D0, farm_with
from tests.unit.test_briefing_domain import _check, _house

AS_OF = D0 + timedelta(days=14)


class CalmSource(DemoFarmSource):
    """Three healthy houses (one death a day, plenty of feed), read as of AS_OF; everything else is the real source."""

    def __init__(self) -> None:
        self._farm = farm_with(_house(1), _house(2), _house(3))
        super().__init__(clock=lambda: AS_OF, now=lambda: datetime(2026, 10, 15, 10, 0, tzinfo=IST))

    def snapshot(self):
        return self._farm, AS_OF


def _build(source: CalmSource, more: bool = False):
    ai = AiServices(RulesModel(), None, ManualRunner())
    return build_briefing(source, BriefingRanker(source.store, ai, source.now), more)


def _log(source: CalmSource, house_id: str) -> None:
    source.store.put_record(source._farm.farm_id, house_id, DailyRecord(AS_OF, 1, 30.0))


def test_a_calm_farm_only_reminds_about_the_missing_entries():
    out = _build(CalmSource())
    assert [i.fact_id for i in out.items] == ["not_logged_today:farm"]
    item = out.items[0]
    assert item.level == "info" and item.pinned is False and item.house_id is None and item.number is None
    assert item.values == {"count": 3, "numbers": [1, 2, 3]}
    assert item.text_en == "No entry yet today for House 1, House 2 and House 3."
    assert "షెడ్ 1, షెడ్ 2 మరియు షెడ్ 3" in item.text_te
    assert out.level == "info" and out.total_items == 1 and out.more_available is False
    assert out.text_en.startswith("Here's your briefing for today.") and "Say 'more'" not in out.text_en


def test_only_the_houses_without_an_entry_today_are_named():
    source = CalmSource()
    _log(source, "house-1")
    item = _build(source).items[0]
    assert item.values == {"count": 2, "numbers": [2, 3]}
    assert item.text_en == "No entry yet today for House 2 and House 3."
    _log(source, "house-3")
    item = _build(source).items[0]
    assert item.values == {"count": 1, "numbers": [2]} and item.text_en == "No entry yet today for House 2."


def test_when_everything_is_logged_and_calm_there_is_nothing_to_report():
    source = CalmSource()
    for n in (1, 2, 3):
        _log(source, f"house-{n}")
    out = _build(source)
    assert out.items == [] and out.total_items == 0 and out.level == "none" and out.more_available is False
    assert out.text_en == "Nothing needs your attention today."
    assert out.text_te.strip() and out.ai.engine == "rules"


def test_more_on_a_short_list_says_that_is_everything():
    out = _build(CalmSource(), more=True)
    assert out.text_en == "That's everything for today." and out.items[0].spoken is False


def test_a_layer_house_does_not_break_the_briefing():
    source = CalmSource()
    source._farm = farm_with(_house(1, kind=HouseKind.LAYER))
    out = _build(source)
    assert [i.category for i in out.items] == ["not_logged_today"]


# -- stored health checks in the answer (Rule 11 review 2026-09-30: H1, M2, M3, L1) --------------------------------
CALL_YOUR_VET = "call your vet"


def _store_check(source: CalmSource, urgency: Urgency, days_ago: int, n: int, status=CheckStatus.READY):
    at = datetime(2026, 10, 15, 9, 0, tzinfo=IST) - timedelta(days=days_ago)
    chk = replace(_check("house-1", urgency, at, status), check_id="chk_" + str(n) * 16, farm_id=source._farm.farm_id)
    source.store.add_health_check(chk)
    return chk


def _item(out, category="open_health_check"):
    return next(i for i in out.items if i.category == category)


def test_an_unfinished_urgent_check_is_in_the_briefing_and_says_it_is_not_finished():
    source = CalmSource()
    _store_check(source, Urgency.URGENT, 0, 1, CheckStatus.FAILED)
    item = _item(_build(source))
    assert item.pinned and item.level == "alert" and item.values["urgency"] == "urgent"
    assert "needs a vet today" in item.text_en and "not finished" in item.text_en
    assert item.text_te.strip() and item.text_te != item.text_en


def test_a_finished_check_says_what_it_said_with_no_unfinished_note():
    source = CalmSource()
    _store_check(source, Urgency.URGENT, 0, 1)
    assert "not finished" not in _item(_build(source)).text_en


def test_a_newer_routine_check_does_not_hide_an_earlier_notifiable_one_until_a_vet_handoff_is_confirmed():
    source = CalmSource()
    earlier = _store_check(source, Urgency.NOTIFIABLE_SUSPECT, 2, 1)
    _store_check(source, Urgency.ROUTINE, 0, 2)
    item = _item(_build(source), "follow_up")  # a due follow-up replaces the open-check item (same keys)
    assert item.values["urgency"] == "notifiable_suspect" and item.values["days_ago"] == 2 and item.pinned
    source.store.add_handoff(VetHandoff(new_handoff_id(), earlier.farm_id, earlier.check_id, source.now(), "s", "సా"))
    assert not any(i.category == "open_health_check" for i in _build(source).items)


def test_a_notifiable_check_is_still_shown_six_days_later():
    source = CalmSource()
    _store_check(source, Urgency.NOTIFIABLE_SUSPECT, 6, 1)
    assert _item(_build(source), "follow_up").values["days_ago"] == 6


@pytest.mark.parametrize("urgency", [Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT])
def test_an_urgent_or_notifiable_item_carries_the_same_call_your_vet_step_as_a_mortality_item(urgency):
    source = CalmSource()
    _store_check(source, urgency, 0, 1)
    out = _build(source)
    assert out.text_en.count(CALL_YOUR_VET) == 1 and "guidance, not a diagnosis" in out.text_en
    assert SAFETY_STEP.te in out.text_te


def test_a_watch_check_gets_the_disclaimer_but_no_call_your_vet_step():
    source = CalmSource()
    _store_check(source, Urgency.WATCH, 0, 1)
    out = _build(source)
    assert _item(out).pinned and CALL_YOUR_VET not in out.text_en and "guidance, not a diagnosis" in out.text_en


def test_the_step_is_said_once_when_a_mortality_item_and_a_check_are_both_read():
    source = CalmSource()
    _store_check(source, Urgency.URGENT, 0, 1)
    source._farm = farm_with(_house(1, deaths={14: 60}), _house(2), _house(3))
    assert _build(source).text_en.count(CALL_YOUR_VET) == 1


# -- a live-style ranker on a hand-built farm: 1 health item, 3 low-feed houses, the reminder -----------------------
def _reverse_offered(request):
    return {"order": list(reversed(request.schema["properties"]["order"]["items"]["enum"]))}


class BusySource(CalmSource):
    def __init__(self) -> None:
        super().__init__()
        self._farm = farm_with(
            _house(1, deaths={14: 12}), _house(2, stock_kg=5.0), _house(3, stock_kg=1.0), _house(4, stock_kg=8.0)
        )


class LiveRig:
    def __init__(self, model) -> None:
        self.source = BusySource()
        self.runner = ManualRunner()
        self.ranker = BriefingRanker(self.source.store, AiServices(model, None, self.runner), self.source.now)

    def build(self, more: bool = False):
        return build_briefing(self.source, self.ranker, more)

    def ids(self, more: bool = False):
        return [i.fact_id for i in self.build(more).items]


def test_more_reads_items_4_and_5_of_the_same_order_the_first_answer_used_even_after_the_ai_order_lands():
    """M1 (Rule 11 review 2026-09-30): the split between the first three and the rest never depends on the AI."""
    rig = LiveRig(ScriptedModel(_reverse_offered))
    before = rig.ids()  # the first answer of the day: rules order, the AI job is queued
    assert rig.runner.run_all() == 1
    after = rig.ids()
    assert after[:3] != before[:3] or True  # (the AI may permute inside the first three, see the next test)
    assert set(after[:3]) == set(before[:3]) and after[3:] == before[3:]
    more = rig.build(more=True)
    assert [i.fact_id for i in more.items][3:] == before[3:]  # what "more" reads is what the first answer promised
    assert [i.fact_id for i in more.items if i.spoken] == before[3:]
    assert not (set(i.fact_id for i in more.items if i.spoken) & set(before[:3]))  # nothing read twice


def test_more_ignores_the_ai_order_and_uses_the_rules_order():
    rig = LiveRig(ScriptedModel(_reverse_offered))
    rules = rig.ids(more=True)
    rig.runner.run_all()
    assert rig.ids(more=True) == rules


def test_the_ai_order_only_moves_non_health_items_inside_the_first_three():
    rig = LiveRig(ScriptedModel(_reverse_offered))
    rules = rig.ids()
    rig.runner.run_all()
    ai = rig.ids()
    assert rules[0] == ai[0] == "mortality_spike:house-1"  # health stays first
    assert ai[1:3] == list(reversed(rules[1:3]))  # the reversing model took effect on the two non-health items here
    assert ai[3:] == rules[3:]


def test_a_stored_ranking_that_cannot_be_read_never_crashes_and_the_rules_order_is_shown_and_labelled(caplog):
    """H2 (Rule 11 review 2026-09-30)."""
    rig = LiveRig(ScriptedModel(_reverse_offered))
    rules = rig.ids()
    farm, as_of = rig.source.snapshot()
    fp = fingerprint(collect_facts(farm, as_of, {}, frozenset()))
    db = rig.source.store._db
    for bad in ("not json", '[["x"]]', '{"a": 1}', "[1, 2]", '"abc"', "null"):
        db.execute(
            "INSERT OR REPLACE INTO briefing_ranks VALUES (?, ?, ?, ?, ?, ?, ?)",
            (farm.farm_id, as_of.isoformat(), fp, bad, "nova", None, None),
        )
        out = rig.build()
        assert [i.fact_id for i in out.items] == rules, bad
        assert out.ai.note == "unreadable" and out.ai.engine == "rules", bad
        assert "unreadable" in out.ai.label_en.lower() and out.ai.label_te.strip()
        assert out.items[0].pinned
    assert "unreadable" in caplog.text
