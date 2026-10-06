"""Step 52 part A: a second log of deaths on the same day (Asia/Kolkata) is NEVER silently added or replaced.

The farmer counts once each morning, so a second number is most likely a correction. When the house already has deaths
for today the read-back shows the old and the new number and asks: add (the sum) or replace (the new number, saying
which old value goes). A plain yes is not an answer to that question; only add, replace or no is. The first log
of a day, and any other day, are exactly as before. The demo behaves as it always did."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from clucktalk.domain.errors import DeathsExceedLiveBirds
from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.farm_state import IST, DemoFarmSource, PilotFarmSource
from clucktalk.server.tools.records import build_log_record
from tests.crossmodal import spoken_numbers, unbacked_numbers

ROOT = Path(__file__).resolve().parents[2]
D1 = date(2026, 10, 9)
D2 = date(2026, 10, 10)


class Rig:
    def __init__(self) -> None:
        self.day = [D1]
        self.source = PilotFarmSource(
            load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json"),
            clock=lambda: self.day[0],
            now=lambda: datetime.combine(self.day[0], datetime.min.time(), IST).replace(hour=8),
        )
        self.flow = ConfirmFlow(self.source.store, self.source.now)

    def call(self, house="shed 1", deaths=None, feed=None, pid=None, answer=None, choice=None, day=None):
        return build_log_record(self.source, self.flow, house, day, deaths, feed, None, None, None, pid, answer, choice)

    def deaths(self, house="house-1", day=D1):
        rec = next((r for r in self.source.store.records(self.source.farm_id, house) if r.day == day), None)
        return None if rec is None else rec.deaths

    def log(self, deaths, how="yes", **kw):
        first = self.call(deaths=deaths, **kw)
        answer = "yes" if how in ("add", "replace", "yes") else "no"
        choice = how if how in ("add", "replace") else None
        done = self.call(deaths=deaths, pid=first.proposal_id, answer=answer, choice=choice, **kw)
        return first, done


@pytest.fixture
def rig():
    return Rig()


def test_the_first_log_of_the_day_is_exactly_as_before(rig):
    first = rig.call(deaths=3)
    assert first.status == "needs_confirmation" and first.choice is None
    assert first.text_en == "For House 1, today: 3 died. Say yes to save, or no to keep it as it is."
    done = rig.call(deaths=3, pid=first.proposal_id, answer="yes")
    assert done.status == "changed" and rig.deaths() == 3


def test_a_second_log_asks_and_shows_both_numbers_and_changes_nothing(rig):
    rig.log(3)
    second = rig.call(deaths=2)
    assert second.status == "needs_confirmation" and second.proposal_id
    assert (second.choice.existing_deaths, second.choice.new_deaths, second.choice.total_if_added) == (3, 2, 5)
    assert second.text_en == ("House 1: 3 died today so far. Add 2 to make 5, or replace 3 with 2?")
    assert "చనిపోయాయి" in second.text_te and "5" in second.text_te
    assert "Say yes" not in second.text_en and "'అవును'" not in second.text_te  # not a yes or no question
    assert rig.deaths() == 3  # asking changes nothing


def test_add_gives_the_sum(rig):
    rig.log(3)
    first, done = rig.log(2, how="add")
    assert done.status == "changed" and rig.deaths() == 5


def test_replace_gives_the_new_number_and_the_question_showed_the_old_one(rig):
    rig.log(3)
    first, done = rig.log(2, how="replace")
    assert "replace 3 with 2" in first.text_en and done.status == "changed" and rig.deaths() == 2


def test_no_keeps_the_old_record(rig):
    rig.log(3)
    first, done = rig.log(2, how="no")
    assert done.status == "cancelled" and rig.deaths() == 3


def test_a_plain_yes_is_not_accepted_and_the_question_stays_open(rig):
    rig.log(3)
    first = rig.call(deaths=2)
    plain = rig.call(deaths=2, pid=first.proposal_id, answer="yes")
    assert plain.status == "needs_confirmation" and plain.proposal_id == first.proposal_id  # asked again, same proposal
    assert plain.choice is not None and rig.deaths() == 3
    again = rig.call(deaths=2, pid=first.proposal_id, answer="yes")
    assert again.status == "needs_confirmation" and rig.deaths() == 3
    done = rig.call(
        deaths=2, pid=first.proposal_id, answer="yes", choice="add"
    )  # the same proposal can still be answered
    assert done.status == "changed" and rig.deaths() == 5


def test_three_logs_in_one_day_each_ask_and_each_is_explicit(rig):
    rig.log(3)
    rig.log(2, how="add")  # 5
    first = rig.call(deaths=4)
    assert (first.choice.existing_deaths, first.choice.total_if_added) == (5, 9)
    rig.call(deaths=4, pid=first.proposal_id, answer="yes", choice="add")
    assert rig.deaths() == 9
    rig.log(1, how="replace")
    assert rig.deaths() == 1


def test_a_sum_above_the_birds_is_refused_by_the_existing_check_and_nothing_changes(rig):
    rig.log(2900)  # house 1 has 3000 birds
    first = rig.call(deaths=200)
    assert (first.choice.total_if_added) == 3100
    with pytest.raises(DeathsExceedLiveBirds):
        rig.call(deaths=200, pid=first.proposal_id, answer="yes", choice="add")
    assert rig.deaths() == 2900
    done = rig.call(deaths=200, pid=first.proposal_id, answer="yes", choice="replace")  # 200 alone is fine
    assert done.status == "changed" and rig.deaths() == 200


def test_a_number_above_the_birds_is_refused_at_the_first_call_as_before(rig):
    rig.log(5)
    with pytest.raises(DeathsExceedLiveBirds):
        rig.call(deaths=3001)


def test_another_day_is_logged_as_before_and_does_not_ask(rig):
    rig.log(3)
    rig.day[0] = D2  # the next morning
    first = rig.call(deaths=4)
    assert first.choice is None and first.text_en.startswith("For House 1, today: 4 died.")
    rig.call(deaths=4, pid=first.proposal_id, answer="yes")
    assert rig.deaths(day=D1) == 3 and rig.deaths(day=D2) == 4


def test_a_backdated_log_for_a_day_with_deaths_asks_too(rig):
    rig.log(3)
    rig.day[0] = D2
    first = rig.call(deaths=1, day=D1)
    assert first.choice is not None and (first.choice.existing_deaths, first.choice.total_if_added) == (3, 4)
    assert "on Friday" in first.text_en or "Friday" in first.text_en


def test_a_house_with_no_deaths_yet_today_does_not_ask_even_if_feed_was_logged(rig):
    first = rig.call(feed=2)
    rig.call(feed=2, pid=first.proposal_id, answer="yes")  # a record exists today with 0 deaths
    second = rig.call(deaths=3)
    assert second.choice is None and second.status == "needs_confirmation"
    assert second.text_en.endswith("Say yes to save, or no to keep it as it is.")


def test_the_same_number_again_still_asks_because_add_and_replace_differ(rig):
    rig.log(3)
    again = rig.call(deaths=3)
    assert again.status == "needs_confirmation" and (again.choice.total_if_added) == 6


def test_the_other_houses_are_independent(rig):
    rig.log(3)
    first = rig.call(house="shed 2", deaths=2)
    assert first.choice is None


def test_other_fields_in_the_same_call_are_read_back_with_the_question(rig):
    rig.log(3)
    first = rig.call(deaths=2, feed=2)
    assert first.choice is not None and "2 bags of feed" in first.text_en
    rig.call(deaths=2, feed=2, pid=first.proposal_id, answer="yes", choice="replace")
    rec = next(r for r in rig.source.store.records(rig.source.farm_id, "house-1") if r.day == D1)
    assert rec.deaths == 2 and rec.feed_kg == 100.0


def test_every_number_in_the_question_is_backed_by_the_structured_answer(rig):
    rig.log(3)
    out = rig.call(deaths=2).model_dump(mode="json")
    assert unbacked_numbers(out, out["text_en"], out["text_te"]) == []
    assert sorted(spoken_numbers(out["text_en"], set())) == sorted(spoken_numbers(out["text_te"], set()))


def test_an_expired_question_cannot_be_answered(rig):
    rig.log(3)
    first = rig.call(deaths=2)
    rig.source.now = lambda: datetime(2026, 10, 9, 20, 0, tzinfo=IST)  # long after the ten minutes
    rig.flow = ConfirmFlow(rig.source.store, rig.source.now)
    done = rig.call(deaths=2, pid=first.proposal_id, answer="yes", choice="add")
    assert done.status != "changed" and rig.deaths() == 3


def test_the_demo_keeps_its_old_wording_and_behaviour():
    source = DemoFarmSource(clock=lambda: D1)
    flow = ConfirmFlow(source.store, source.now)
    first = build_log_record(source, flow, "shed 1", None, 7, None, None, None, None, None, None)
    assert (
        first.choice is None and "I'll add this to it" in first.text_en and first.text_en.endswith("keep it as it is.")
    )
    done = build_log_record(source, flow, "shed 1", None, 7, None, None, None, None, first.proposal_id, "yes")
    assert done.status == "changed"


def test_the_day_belongs_to_the_asia_kolkata_date_at_the_boundary(monkeypatch):
    import clucktalk.server.farm_state as fs

    moment = [datetime(2026, 10, 9, 18, 29, 59, tzinfo=UTC)]  # 23:59:59 in India

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment[0].astimezone(tz)

    monkeypatch.setattr(fs, "datetime", FakeDatetime)
    assert fs.today_ist() == date(2026, 10, 9)
    moment[0] = datetime(2026, 10, 9, 18, 30, 0, tzinfo=UTC)  # 00:00:00 the next day in India
    assert fs.today_ist() == date(2026, 10, 10)
    source = PilotFarmSource(load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json"))
    flow = ConfirmFlow(source.store, source.now)
    moment[0] = datetime(2026, 10, 9, 18, 29, 59, tzinfo=UTC)
    first = build_log_record(source, flow, "shed 1", None, 3, None, None, None, None, None, None)
    build_log_record(source, flow, "shed 1", None, 3, None, None, None, None, first.proposal_id, "yes")
    moment[0] = datetime(2026, 10, 9, 18, 30, 1, tzinfo=UTC) + timedelta(seconds=0)
    nxt = build_log_record(source, flow, "shed 1", None, 5, None, None, None, None, None, None)
    assert nxt.choice is None, "after midnight in India it is a new day: the first log of the day does not ask"
    moment[0] = datetime(2026, 10, 9, 18, 29, 58, tzinfo=UTC)
    before = build_log_record(source, flow, "shed 1", None, 5, None, None, None, None, None, None)
    assert before.choice is not None, "just before midnight in India it is still the same day: it asks"
