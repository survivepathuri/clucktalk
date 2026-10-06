"""Step 52 part A: no sequence of logs, answers and day changes ever changes a record's deaths without an explicit
add or replace (or, on a day with no deaths yet, the ordinary yes). A model of "what the farmer explicitly chose" is
replayed against the real tool after every step."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from clucktalk.domain.errors import DeathsExceedLiveBirds
from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.farm_state import IST, PilotFarmSource
from clucktalk.server.tools.records import build_log_record

ROOT = Path(__file__).resolve().parents[2]
START = date(2026, 10, 9)
PROPERTY = settings(
    max_examples=60, derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow], database=None
)

# (kind, number): ask a log, then answer it in one of several ways, or move to the next day.
actions = st.one_of(
    st.tuples(st.just("log"), st.integers(0, 60)),
    st.tuples(st.sampled_from(["yes", "add", "replace", "no", "ignore"]), st.just(0)),
    st.tuples(st.just("nextday"), st.just(0)),
)


@PROPERTY
@given(st.lists(actions, max_size=14))
def test_a_record_changes_only_by_an_explicit_choice(sequence):
    day = [START]
    source = PilotFarmSource(
        load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json"),
        clock=lambda: day[0],
        now=lambda: datetime.combine(day[0], datetime.min.time(), IST).replace(hour=8),
    )
    flow = ConfirmFlow(source.store, source.now)
    model: dict[date, int] = {}  # what the farmer has explicitly chosen to be stored
    pending: dict | None = None

    def stored(d: date) -> int | None:
        rec = next((r for r in source.store.records(source.farm_id, "house-1") if r.day == d), None)
        return None if rec is None else rec.deaths

    for kind, n in sequence:
        if kind == "log":
            out = build_log_record(source, flow, "shed 1", None, n, None, None, None, None, None, None)
            pending = {
                "deaths": n,
                "pid": out.proposal_id,
                "day": day[0],
                "asked": out.choice is not None,
                "live": True,
            }
        elif kind == "nextday":
            day[0] += timedelta(days=1)
            pending = (
                None if pending is None else {**pending, "live": False}
            )  # a new day's morning: old question is stale
        elif pending is not None and pending["pid"] is not None:
            choice = kind if kind in ("add", "replace") else None
            answer = "no" if kind == "no" else "yes"
            if kind == "ignore":
                continue
            before = {d: stored(d) for d in (START + timedelta(days=i) for i in range(16))}
            try:
                out = build_log_record(
                    source, flow, "shed 1", None, pending["deaths"], None, None, None, None,
                    pending["pid"], answer, choice,
                )  # fmt: skip
            except DeathsExceedLiveBirds:
                assert {d: stored(d) for d in before} == before  # a refused answer changes nothing
                continue
            after = {d: stored(d) for d in before}
            if out.replayed:
                assert after == before  # a repeated answer to a confirmed question changes nothing
                continue
            changed = {d for d in before if before[d] != after[d]}
            if out.status == "changed":
                d = pending["day"]
                assert changed <= {d}
                if pending["asked"]:
                    assert choice in ("add", "replace"), "a record changed on a plain yes"
                    expected = (before[d] or 0) + pending["deaths"] if choice == "add" else pending["deaths"]
                    assert after[d] == expected
                else:
                    assert after[d] == pending["deaths"]
                model[d] = after[d]
            else:
                assert not changed, f"a record changed without a change being confirmed: {out.status}"
        assert {d: stored(d) for d in model} == model  # nothing the farmer chose was altered behind his back
