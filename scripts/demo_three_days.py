"""Build the demo-clock state file for the "three days later" recording (mock mode, no AWS).

Makes the Session 4 MCP calls over real HTTP against an in-process server whose state is the demo-clock file (never the
live state file):
    day 0 (clock +0): a health check on shed one with a cough (watch) and one on shed two (urgent, the seeded spike);
    day 1 (clock +1): the "worse" answer for shed two, read back and confirmed.
Then prints the command that serves the demo clock at +3 and the basic-host URLs. The demo clock shifts follow-up and
briefing dates only: flock ages, record-book entries and the sale plan do not move.

Usage (Windows):  python tasks.py demo-three-days     (refuses live mode; refuses an existing demo-clock file)
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import httpx2  # noqa: E402
import uvicorn  # noqa: E402

from clucktalk.config import ConfigError, load_settings  # noqa: E402
from clucktalk.server.app import MCP_PATH, build_app, build_mcp_server  # noqa: E402
from clucktalk.server.farm_state import DemoClock, DemoFarmSource  # noqa: E402
from clucktalk.store import StoreError  # noqa: E402
from clucktalk.store.sqlite import SqliteStore  # noqa: E402

DAYS_LATER = 3  # the recording serves the clock at +3
_spec = importlib.util.spec_from_file_location("eval_fast_helpers", ROOT / "scripts" / "eval_fast.py")
_ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ev)  # type: ignore[union-attr]  # the eval runner's HTTP helpers: one place for them


class StepFailed(RuntimeError):
    pass


def _call(client: httpx2.Client, url: str, headers: dict[str, str], tool: str, **args: Any) -> dict[str, Any]:
    sc, error = _ev._call(client, url, headers, tool, args)
    if sc is None:
        raise StepFailed(f"{tool}({args}): {error}")
    return sc


def _expect(what: str, actual: Any, wanted: Any) -> None:
    if actual != wanted:
        raise StepFailed(f"{what}: expected {wanted!r}, got {actual!r}")


def _run_day(settings, env: Mapping[str, str], days_later: int, steps) -> None:
    """One server run on the demo-clock file at clock ``+days_later``; ``steps`` makes the calls over HTTP."""
    store = SqliteStore(settings.demo_clock_state_path, demo_clock=True)
    port = _ev._free_port()
    source = DemoFarmSource(store=store, demo_clock=DemoClock(days_later))
    app = build_app(load_settings({**env, "CLUCKTALK_PORT": str(port)}), build_mcp_server(source))
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not uv.started:
            if time.monotonic() > deadline or not thread.is_alive():
                raise StepFailed("the MCP server did not start")
            time.sleep(0.02)
        with httpx2.Client(timeout=10) as client:
            url = f"http://127.0.0.1:{port}{MCP_PATH}"
            steps(client, url, _ev._session(client, url))
    finally:
        uv.should_exit = True
        thread.join(timeout=10)
        store.close()


def _day_zero(client, url, headers) -> None:
    one = _call(client, url, headers, "start_health_check", house="shed one", signs=["coughing"])
    _expect("shed one status", one["status"], "analyzing")
    _expect("shed one follow-up in days", one["follow_up_in_days"], 3)
    two = _call(client, url, headers, "start_health_check", house="shed two", signs=["coughing", "sneezing"])
    _expect("shed two floor urgency", two["floor_urgency"], "urgent")
    for check_id in (one["check_id"], two["check_id"]):
        deadline = time.monotonic() + 10
        while _call(client, url, headers, "get_health_check", check_id=check_id)["status"] == "analyzing":
            if time.monotonic() > deadline:
                raise StepFailed(f"check {check_id} did not finish")
            time.sleep(0.1)


def _day_one(client, url, headers) -> None:
    asked = _call(client, url, headers, "report_health_follow_up", house="shed two", outcome="worse")
    _expect("the worse answer's read-back", asked["status"], "needs_confirmation")
    done = _call(
        client, url, headers, "report_health_follow_up",
        house="shed two", outcome="worse", proposal_id=asked["proposal_id"], answer="yes",
    )  # fmt: skip
    _expect("the worse answer", (done["status"], done["state"]), ("changed", "escalated"))


def main(env: Mapping[str, str] | None = None) -> int:
    env = dict(os.environ if env is None else env)
    logging.basicConfig(level=logging.WARNING)  # the server's per-request INFO lines would bury the result
    try:  # the demo clock is demo mode only: live mode is refused here exactly as the server refuses it
        settings = load_settings({**env, "CLUCKTALK_DEMO_DAYS_LATER": str(DAYS_LATER)})
    except ConfigError as exc:
        print(f"demo-three-days: {exc}", file=sys.stderr)
        return 2
    path = settings.demo_clock_state_path
    if path.exists() or path.with_name(path.name + "-journal").exists():
        print(
            f"demo-three-days: {path} already exists, so it is not changed. "
            "Start fresh with: python tasks.py reset-demo --yes",
            file=sys.stderr,
        )
        return 2
    try:
        _run_day(settings, env, 0, _day_zero)
        _run_day(settings, env, 1, _day_one)
    except (StepFailed, StoreError, OSError) as exc:  # fail loud: a half-built file is never presented as ready
        print(f"demo-three-days: FAILED: {exc}. The partly built file {path} stays for inspection; "
              "python tasks.py reset-demo --yes clears it.", file=sys.stderr)  # fmt: skip
        return 1
    print(f"demo-three-days: built {path} (demo-clock state; the live farm state file was not opened).")
    print("  day 0: shed one watch check, shed two urgent check (seeded spike). day 1: shed two answered 'worse'.")
    print("Next, serve the demo clock at +3 (follow-up and briefing dates only; flock ages, record-book entries and")
    print("the sale plan do not move):")
    print("  set CLUCKTALK_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080   (only for basic-host)")
    print(f"  python tasks.py serve --demo-days-later {DAYS_LATER}")
    print('Then open in basic-host (ext-apps examples/basic-host, SERVERS=["http://127.0.0.1:8765/mcp"]):')
    print("  http://localhost:8080/   server CluckTalk, tools get_daily_briefing and get_farm_status")
    print("  MCP endpoint: http://127.0.0.1:8765/mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
