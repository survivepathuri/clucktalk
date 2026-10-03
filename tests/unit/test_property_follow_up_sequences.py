"""Step 48B part A: property-based tests of the health-check / follow-up / vet-handoff / record-book sequence.

Hypothesis builds random sequences of the events a farmer can cause (a health check of any urgency, an answer, a death
record, a vet handoff, a newer check, the demo clock moving forward) and replays each on a fresh in-memory farm. After
every event it asserts the safety invariants. The tools are called in process (``mcp.Client(server)``), not over HTTP,
so a run is fast. Settings are fixed: derandomized, capped examples, no deadline (Windows timers, FL-023).

Invariants (each is one function below, named for what it protects):
  told urgency never changes; an escalated follow-up with no handoff and no equal-or-higher newer check stays
  escalated; every not-better answer says "To be safe, contact your vet or doctor."; an escalated or due follow-up is
  on the shed's level and visible; briefing level, farm-status level and the safety field agree; confirming the same
  answer or handoff twice adds nothing; nothing raises and every error result is structured."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import anyio
import pytest
from hypothesis import HealthCheck as HypothesisHealthCheck
from hypothesis import given, settings
from hypothesis import strategies as st
from mcp import Client

from clucktalk.domain.follow_up import EscalationReason, FollowUpState, follow_up_state
from clucktalk.domain.models import DailyRecord
from clucktalk.domain.triage import (
    CheckStatus,
    Floor,
    HealthCheck,
    Sign,
    TriageInput,
    TriageResult,
    Urgency,
    new_check_id,
)
from clucktalk.server.app import build_mcp_server
from clucktalk.server.farm_state import IST, DemoClock, DemoFarmSource
from clucktalk.server.tools.follow_up import TO_BE_SAFE

BASE = datetime(2026, 9, 29, 10, 0, tzinfo=IST)
HOUSES = (1, 2, 3)
OUTCOMES = ("better", "same", "worse", "not_sure")
LEVEL_WORD = {"ok": "OK", "info": "OK", "none": "OK", "watch": "WATCH", "alert": "ALERT", "unknown": "UNKNOWN"}
LEVEL_WORD_INV = {"OK": "ok", "WATCH": "watch", "ALERT": "alert", "UNKNOWN": "watch"}
RANK = {"ok": 0, "info": 0, "none": 0, "watch": 1, "alert": 2}
HEALTH_CATEGORIES = ("open_health_check", "follow_up")

PROPERTY = settings(
    max_examples=100,
    derandomize=True,  # the same examples on every run and every OS
    deadline=None,  # Windows timer granularity (FL-023)
    suppress_health_check=[HypothesisHealthCheck.too_slow],
    database=None,
)


# -- the events ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Check:
    house: int
    urgency: Urgency


@dataclass(frozen=True)
class Answer:
    house: int
    outcome: str


@dataclass(frozen=True)
class Record:
    house: int
    days_ago: int
    deaths: int


@dataclass(frozen=True)
class Handoff:
    house: int


@dataclass(frozen=True)
class MoveClock:
    days: int


events = st.one_of(
    st.builds(Check, st.sampled_from(HOUSES), st.sampled_from(list(Urgency))),
    st.builds(Answer, st.sampled_from(HOUSES), st.sampled_from(OUTCOMES)),
    st.builds(Record, st.sampled_from(HOUSES), st.integers(0, 2), st.sampled_from([0, 1, 5, 60, 400])),
    st.builds(Handoff, st.sampled_from(HOUSES)),
    st.builds(MoveClock, st.integers(1, 9)),
)
sequences = st.lists(events, max_size=8)


# -- the world -------------------------------------------------------------------------------------------------------
class World:
    def __init__(self) -> None:
        self.clock = DemoClock(0, real_now=lambda: BASE)
        self.source = DemoFarmSource(demo_clock=self.clock)
        self.server = build_mcp_server(self.source)
        self.checks_made = 0
        self.told: dict[str, str] = {}  # check id -> the urgency code it was stored with
        self.client: Client

    @property
    def store(self):
        return self.source.store

    def add_check(self, house: int, urgency: Urgency) -> str:
        self.checks_made += 1
        at = self.clock.now() + timedelta(minutes=self.checks_made)  # strictly later than every earlier check
        house_id = f"house-{house}"
        inp = TriageInput(house_id, f"House {house}", f"షెడ్ {house}", "Ross 308", 40, 900, (Sign.COUGHING,), None, None,
                          None, 2, 1.0, False, None, at.date().isoformat())  # fmt: skip
        result = TriageResult(urgency, (), (), "rules", None, None)
        check = HealthCheck(
            new_check_id(), self.source.farm_id, house_id, at, CheckStatus.READY, inp, Floor(urgency, ()), result, at
        )
        self.store.add_health_check(check)
        self.told[check.check_id] = urgency.code
        return check.check_id

    async def call(self, tool: str, **args: Any) -> Any:
        return await self.client.call_tool(tool, args)

    async def confirmed(self, tool: str, **args: Any) -> tuple[Any, Any, Any] | None:
        """The two-step flow, then the same "yes" again. None when the first call is refused (a legal rejection)."""
        first = await self.call(tool, **args)
        if first.is_error:
            assert_structured_error(first)
            return None
        sc = first.structured_content
        if sc["status"] != "needs_confirmation":  # e.g. "already_set": the vet already has this summary
            assert sc["status"] in ("already_set", "cancelled"), sc
            return None
        second = await self.call(tool, **args, proposal_id=sc["proposal_id"], answer="yes")
        assert not second.is_error, second
        again = await self.call(tool, **args, proposal_id=sc["proposal_id"], answer="yes")
        return first, second, again

    def counts(self) -> tuple[int, int]:
        db = self.store._db
        answers = db.execute("SELECT COUNT(*) FROM follow_up_answers").fetchone()[0]
        handoffs = db.execute("SELECT COUNT(*) FROM vet_handoffs").fetchone()[0]
        return answers, handoffs


def assert_structured_error(result: Any) -> None:
    """A rejected call is a tool error with a spoken sentence and no traceback; never an exception."""
    assert result.is_error
    text = " ".join(c.text for c in result.content if getattr(c, "text", None))
    assert text.strip() and "Traceback" not in text and 'File "' not in text, text


# -- applying events, with the invariants that belong to one event -------------------------------------------------
async def apply(world: World, event: Any) -> None:
    before_counts = world.counts()
    match event:
        case Check(house, urgency):
            world.add_check(house, urgency)
        case Record(house, days_ago, deaths):
            day = world.clock.today() - timedelta(days=days_ago)
            world.store.put_record(world.source.farm_id, f"house-{house}", DailyRecord(day, deaths, 100.0))
        case MoveClock(days):
            world.clock.set_days_later(min(30, world.clock.days_later + days))
        case Answer(house, outcome):
            steps = await world.confirmed("report_health_follow_up", house=f"shed {house}", outcome=outcome)
            if steps is not None:
                first, second, again = steps
                if outcome != "better":
                    for result in (first, second):  # the read-back and the saved answer both say it
                        sc = result.structured_content
                        assert TO_BE_SAFE.en in sc["text_en"] and TO_BE_SAFE.te in sc["text_te"], sc["text_en"]
                assert again.structured_content["status"] == "changed" and again.structured_content["replayed"]
                assert world.counts()[0] == before_counts[0] + 1, "an answer confirmed twice was saved twice"
        case Handoff(house):
            steps = await world.confirmed("prepare_vet_handoff", house=f"shed {house}")
            if steps is not None:
                assert world.counts()[1] <= before_counts[1] + 1, "a handoff confirmed twice was saved twice"


# -- the invariants that hold after every event --------------------------------------------------------------------
def follow_ups(world: World) -> dict[str, tuple[Any, Any]]:
    """Every stored check's follow-up, worked out with the domain function straight from the store."""
    farm, today = world.source.snapshot()
    out: dict[str, tuple[Any, Any]] = {}
    for house in farm.houses:
        checks = world.store.recent_health_checks(farm.farm_id, house.house_id, date.min)
        handed = {c.check_id: world.store.handoff_for_check(c.check_id) for c in checks}
        handed = {k: v.created_at for k, v in handed.items() if v is not None}
        for check in checks:
            answers = world.store.follow_up_answers(farm.farm_id, check.check_id)
            out[check.check_id] = (check, follow_up_state(check, answers, handed, house, today, checks))
    return out


def check_told_urgency_never_changes(world: World) -> None:
    for check_id, code in world.told.items():
        check = world.store.get_health_check(check_id)
        assert check is not None and check.result is not None and check.result.urgency.code == code
        assert check.floor.urgency.code == code


async def surfaces(world: World) -> tuple[dict, dict, dict[int, dict]]:
    brief = (await world.call("get_daily_briefing")).structured_content
    farm = (await world.call("get_farm_status")).structured_content
    shed = {}
    for n in HOUSES:
        result = await world.call("get_farm_status", house=f"shed {n}")
        assert not result.is_error, result
        shed[n] = result.structured_content
    return brief, farm, shed


def assert_safety_level_vs_card(safety_level: str, card_level: str, records_logged: bool) -> None:
    if records_logged:
        assert RANK[LEVEL_WORD_INV[safety_level]] >= RANK[card_level], (safety_level, card_level)
    else:
        assert safety_level == LEVEL_WORD[card_level], (safety_level, card_level)


def check_levels_agree(world: World, brief: dict, farm: dict, shed: dict[int, dict], records_logged: bool) -> None:
    assert brief["safety"]["level"] == LEVEL_WORD[brief["level"]], (brief["level"], brief["safety"])
    # Step 48C: the safety level is never lower than the card, and equals it unless a death record was logged (a spike
    # from an earlier day is a briefing fact the status card does not show; the safety field then says ALERT).
    assert_safety_level_vs_card(farm["safety"]["level"], farm["level"], records_logged)
    for n in HOUSES:
        one = shed[n]["houses"][0]
        whole = next(h for h in farm["houses"] if h["house_id"] == f"house-{n}")
        assert one["level"] == whole["level"], (n, one["level"], whole["level"])
        assert_safety_level_vs_card(shed[n]["safety"]["level"], one["level"], records_logged)
        health = [RANK[i["level"]] for i in brief["items"] if i["house_id"] == f"house-{n}"
                  and i["category"] in HEALTH_CATEGORIES]  # fmt: skip
        if not records_logged:  # a logged death record adds briefing / status items the other does not count
            every = [RANK[i["level"]] for i in brief["items"] if i["house_id"] == f"house-{n}"]
            assert RANK[one["level"]] == max(every, default=0), (n, one["level"], brief["items"])
        assert RANK[one["level"]] >= max(health, default=0), (n, one["level"], brief["items"])


def check_briefing_and_status_agree_on_safety(brief: dict, farm: dict, shed: dict[int, dict]) -> None:
    """Step 48C part A: for the same farm state the briefing and the farm status agree on vet_contact_advised, level
    and reason_codes; a shed's status never says more than the whole farm; the sheds together say what it says."""
    assert farm["safety"] == brief["safety"], (farm["safety"], brief["safety"])
    one = [shed[n]["safety"] for n in HOUSES]
    assert all(s["vet_contact_advised"] <= brief["safety"]["vet_contact_advised"] for s in one), (one, brief["safety"])
    assert any(s["vet_contact_advised"] for s in one) == brief["safety"]["vet_contact_advised"], (one, brief["safety"])
    assert all(RANK[LEVEL_WORD_INV[s["level"]]] <= RANK[LEVEL_WORD_INV[brief["safety"]["level"]]] for s in one)
    # (the simulated sale window is a reason only when it is the sole one, so it can differ between a shed and the farm)
    shed_codes = {c for s in one for c in s["reason_codes"]} - {"sale_window"}
    assert set(brief["safety"]["reason_codes"]) >= shed_codes, (one, brief["safety"])


def check_open_follow_ups_are_visible(world: World, brief: dict, farm: dict, shed: dict[int, dict]) -> None:
    for check, fup in follow_ups(world).values():
        n = int(check.house_id.split("-")[1])
        one = shed[n]["houses"][0]
        if fup.state is FollowUpState.ESCALATED:
            assert one["level"] == "alert", (fup, one["level"])
            assert one["follow_up"] is not None or one["open_health_check"] is not None, one
            assert shed[n]["safety"]["vet_contact_advised"] or one["open_health_check"] is not None, shed[n]["safety"]
            assert farm["level"] == "alert" and farm["safety"]["level"] == "ALERT"
        elif fup.state is FollowUpState.DUE:
            assert RANK[one["level"]] >= 1, (fup, one["level"])


def told(check: HealthCheck) -> Urgency:
    return check.result.urgency if check.result is not None else check.floor.urgency


def check_an_open_urgent_check_stays_visible(world: World, shed: dict[int, dict]) -> None:
    """The rule written out without the domain code: an urgent or reportable check that nobody has handed to a vet and
    that no newer check of equal or higher urgency has taken over, and that no "better" has closed, keeps its shed at
    least WATCH forever (a newer lower check never hides it, and it does not lapse after day 8), at ALERT while it is
    at most three days old or once it is escalated, and its follow-up stays on the status."""
    farm, today = world.source.snapshot()
    for house in farm.houses:
        n = house.number
        checks = world.store.recent_health_checks(farm.farm_id, house.house_id, date.min)
        for c in checks:
            urgency = told(c)
            if urgency < Urgency.URGENT or world.store.handoff_for_check(c.check_id) is not None:
                continue
            answers = world.store.follow_up_answers(farm.farm_id, c.check_id)
            if any(a.said.value == "better" for a in answers) and all(a.said.value == "better" for a in answers):
                continue  # closed by the farmer
            if any(o.created_at > c.created_at and told(o) >= urgency for o in checks):
                continue  # taken over by a newer check of equal or higher urgency
            one = shed[n]["houses"][0]
            assert RANK[one["level"]] >= 1, ("open urgent check is hidden", c.check_id, urgency, one)
            age = (today - c.created_at.date()).days
            if age == 0:  # the open check, or (a spike the check did not see) its already escalated follow-up
                assert one["open_health_check"] is not None or one["follow_up"] is not None, one
            else:  # a day on, the status carries its own urgent or reportable follow-up, not a newer lower check
                fu = one["follow_up"]
                assert fu is not None and fu["urgency"] in ("urgent", "notifiable_suspect"), (c.check_id, age, one)
                assert fu["state"] != "closed", fu
            if (today - c.created_at.date()).days <= 3 or (one["follow_up"] or {}).get("state") == "escalated":
                assert one["level"] == "alert", (c.check_id, urgency, (today - c.created_at.date()).days, one)


class Seen:
    """What the sequence has shown so far, to compare one step with the next."""

    def __init__(self) -> None:
        self.escalated: set[str] = set()


def check_escalation_does_not_lapse(world: World, seen: Seen, event: Any) -> None:
    """An escalated follow-up with no vet handoff and no newer check of equal or higher urgency stays escalated (the
    answers it rests on are never removed). A handoff, a newer check of equal or higher urgency, or a clock move that
    changes which death records count are the ways out, so they are excluded."""
    now = follow_ups(world)
    for check_id in list(seen.escalated):
        check, fup = now[check_id]
        newer_same_or_higher = any(
            other.house_id == check.house_id
            and other.created_at > check.created_at
            and (other.result.urgency if other.result else other.floor.urgency) >= fup.urgency
            for other, _ in now.values()
        )
        handed = world.store.handoff_for_check(check_id) is not None
        if handed or newer_same_or_higher or isinstance(event, MoveClock):
            seen.escalated.discard(check_id)
            continue
        assert fup.state is FollowUpState.ESCALATED, (check_id, fup.state, event)
    # Only escalations that rest on a stored answer are tracked: an answer is append-only, whereas a death record can be
    # corrected on its own day, which legitimately removes a spike-based escalation.
    said = {EscalationReason.SAID_SAME, EscalationReason.SAID_WORSE, EscalationReason.SAID_NOT_SURE}
    seen.escalated |= {
        cid for cid, (_, f) in now.items() if f.state is FollowUpState.ESCALATED and said & set(f.reasons)
    }


async def replay(sequence: list[Any]) -> None:
    world = World()
    seen = Seen()
    records_logged = False
    async with Client(world.server) as client:
        world.client = client

        async def no_output_validation(*args: Any, **kwargs: Any) -> None:
            return None  # the output schemas are checked by the contract tests; here it is 60% of the run time

        client.session.validate_tool_result = no_output_validation  # type: ignore[method-assign]
        brief, farm, shed = await surfaces(world)  # the seeded farm before any event
        check_levels_agree(world, brief, farm, shed, records_logged)
        check_briefing_and_status_agree_on_safety(brief, farm, shed)
        for event in sequence:
            await apply(world, event)
            records_logged |= isinstance(event, Record)
            check_told_urgency_never_changes(world)
            check_escalation_does_not_lapse(world, seen, event)
            brief, farm, shed = await surfaces(world)
            check_levels_agree(world, brief, farm, shed, records_logged)
            check_briefing_and_status_agree_on_safety(brief, farm, shed)
            check_open_follow_ups_are_visible(world, brief, farm, shed)
            check_an_open_urgent_check_stays_visible(world, shed)


# Named scenarios the random search might not reach in 100 examples: each is a way a safety rule could be broken.
SCENARIOS = {
    "an urgent check nobody answers is still escalated after day 8": [Check(1, Urgency.URGENT), MoveClock(9)],
    "a newer lower check never hides an escalation": [
        Check(1, Urgency.URGENT),
        MoveClock(1),
        Answer(1, "same"),
        Check(1, Urgency.WATCH),
        MoveClock(2),
    ],
    "a newer lower check never hides an urgent follow-up": [
        Check(1, Urgency.URGENT),
        MoveClock(1),
        Check(1, Urgency.WATCH),
    ],
    "a not-better answer after a vet handoff still says it": [
        Check(1, Urgency.URGENT),
        Handoff(1),
        MoveClock(1),
        Answer(1, "worse"),
    ],
    "better after worse does not close it": [
        Check(1, Urgency.URGENT),
        MoveClock(1),
        Answer(1, "worse"),
        Answer(1, "better"),
    ],
    "a reportable suspect answered but never handed to a vet stays escalated": [
        Check(2, Urgency.NOTIFIABLE_SUSPECT),
        MoveClock(1),
        Answer(2, "better"),
        MoveClock(9),
    ],
    "the same handoff confirmed twice, then a newer check": [
        Check(3, Urgency.URGENT),
        Handoff(3),
        Check(3, Urgency.ROUTINE),
    ],
    "a death record corrected on its own day withdraws a spike-only escalation, nothing else": [
        Check(1, Urgency.WATCH),
        Record(1, 0, 400),
        Record(1, 0, 0),
        MoveClock(3),
    ],
    "an urgent check on the shed whose seeded spike the check did not see is escalated at once": [
        Check(2, Urgency.URGENT)
    ],
    "a death spike logged yesterday: the briefing still advises the vet today and so does the status": [
        Record(1, 0, 60),
        MoveClock(1),
    ],
    "a death spike after a watch check": [Check(1, Urgency.WATCH), MoveClock(1), Record(1, 0, 400), MoveClock(3)],
}


@PROPERTY
@given(sequences)
def test_every_sequence_of_events_keeps_the_safety_invariants(sequence):
    anyio.run(replay, sequence)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_named_scenarios_keep_the_safety_invariants(name):
    anyio.run(replay, SCENARIOS[name])


def test_the_property_runs_stay_inside_the_time_budget():
    import time

    started = time.monotonic()
    anyio.run(replay, [Check(1, Urgency.URGENT), Answer(1, "same"), MoveClock(3), Handoff(1)])
    assert time.monotonic() - started < 5


@pytest.mark.parametrize("urgency", list(Urgency))
def test_a_single_check_of_every_urgency_passes_every_invariant(urgency):
    anyio.run(replay, [Check(1, urgency), MoveClock(2), Answer(1, "worse"), MoveClock(9)])
