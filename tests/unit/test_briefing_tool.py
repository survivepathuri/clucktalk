"""``build_briefing`` on a calm, hand-built farm: the record-book reminder and the "nothing to report" answer, which the
seeded demo farm (always in trouble, by design) can never show. Calls the tool's builder directly, no HTTP."""

from __future__ import annotations

from datetime import datetime, timedelta

from clucktalk.agents import AiServices
from clucktalk.agents.briefing import BriefingRanker
from clucktalk.agents.model import RulesModel
from clucktalk.agents.runner import ManualRunner
from clucktalk.domain.models import DailyRecord, HouseKind
from clucktalk.server.farm_state import IST, DemoFarmSource
from clucktalk.server.tools.briefing import build_briefing
from tests.unit.helpers import D0, farm_with
from tests.unit.test_briefing_domain import _house

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
