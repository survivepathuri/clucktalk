"""Golden eval suite v0 (mock mode, no AWS): runs data/eval/golden_cases.json against a real MCP server over
real HTTP, prints a pass/fail table, and writes docs/EVALS.md. Extended to the full suite later;
this file exists to make `python tasks.py eval-fast` real rather than "not implemented".

Never invents a score: every row is a real HTTP round trip against the same MCP server `tasks.py serve` runs
(CLAUDE.md Rule 5, Rule 6). The demo farm is date-relative, so results do not depend on which day this runs.

Usage (Windows):
    <venv python> scripts/eval_fast.py
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # tests.fakes: the fixture models for fault cases

import httpx2  # noqa: E402
import uvicorn  # noqa: E402

from clucktalk.agents import AiServices  # noqa: E402
from clucktalk.agents.runner import ThreadRunner  # noqa: E402
from clucktalk.config import load_settings  # noqa: E402
from clucktalk.server.app import MCP_PATH, TARGET_PROTOCOL_VERSION, build_app, build_mcp_server  # noqa: E402
from clucktalk.server.farm_state import DemoClock, DemoFarmSource  # noqa: E402
from clucktalk.server.daily_deaths import RuleState, parse_rule  # noqa: E402
from clucktalk.server.weather import Forecast, MockForecast, WeatherReminders, load_weather_config  # noqa: E402
from clucktalk.simulator.intents import match as match_intent  # noqa: E402
from clucktalk.simulator.intents import yes_no  # noqa: E402
from tests.fakes import FIXTURES  # noqa: E402

CASES_PATH = ROOT / "data" / "eval" / "golden_cases.json"
EVALS_MD = ROOT / "docs" / "EVALS.md"
HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
STEP_KEYS = {"tool", "args", "checks", "save", "poll_until", "demo_days_later", "say", "answer_word", "expect_error"}
POLL_SECONDS = 10  # an agent's slow path must finish within this (demo rules take milliseconds)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


WEATHER_NOW = datetime(
    2026, 10, 4, 2, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
)  # the mock curve: 16.0 at 03:00


class _UnavailableForecast:
    def forecast(self, latitude, longitude, now):
        return Forecast("unavailable", (), None, "Open-Meteo", False, "eval: unavailable")


def _weather(spec: str | None):
    """A case's ``weather`` option: the farmer's rules (the same shape as weather_rules.json, validated by the same
    loader) plus ``forecast``: "mock" (default, SIMULATED) or "unavailable". The clock is fixed, so the answer never
    depends on the hour the suite runs."""
    if spec is None:
        return None
    data = json.loads(spec)
    kind = data.pop("forecast", "mock")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "weather_rules.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        config = load_weather_config(path)
    port = _UnavailableForecast() if kind == "unavailable" else MockForecast()
    return WeatherReminders(config, port, lambda: WEATHER_NOW)


class _FixedRule:
    """A case's ``deaths_rule`` option: the farmer's daily deaths rule (the same shape as daily_deaths_rule.json,
    validated by the same parser), read from the case instead of a file."""

    def __init__(self, spec: str) -> None:
        self.state = RuleState(parse_rule(json.loads(spec)), False)

    def current(self) -> RuleState:
        return self.state


def _serve(port: int, fixture: str | None = None, weather: str | None = None, deaths_rule: str | None = None):
    """A fresh mock-mode server (its own in-memory state). ``fixture`` swaps the demo rules for a test model.
    Returns ``(stop, clock)``: the demo clock (off, 0 days) that a case step may move with ``demo_days_later``. That
    hook lives only in this runner, in process: no MCP tool and no argument can reach it (docs/DESIGN.md section 18)."""
    settings = load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_PORT": str(port)})
    clock = DemoClock(0)
    ai = AiServices(model=FIXTURES[fixture](), budget=None, runner=ThreadRunner()) if fixture is not None else None
    source = DemoFarmSource(demo_clock=clock)
    source.weather = _weather(weather)
    source.deaths_rule = None if deaths_rule is None else _FixedRule(deaths_rule)
    server = build_mcp_server(source, ai)
    app = build_app(settings, server)
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not uv.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise SystemExit("eval-fast: the MCP server did not start")
        time.sleep(0.02)

    def stop() -> None:
        uv.should_exit = True
        thread.join(timeout=10)

    return stop, clock


def _session(client: httpx2.Client, url: str) -> dict[str, str]:
    r = client.post(
        url,
        headers=HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": TARGET_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "eval-fast", "version": "0"},
            },
        },
    )
    if r.status_code != 200:
        raise SystemExit(f"eval-fast: initialize failed: {r.status_code} {r.text[:200]}")
    h = {**HEADERS, "mcp-session-id": r.headers["mcp-session-id"], "mcp-protocol-version": TARGET_PROTOCOL_VERSION}
    client.post(url, headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return h


def _get(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(f"{path!r}: no field {part!r} in {list(cur)}")
            cur = cur[part]
        else:
            raise TypeError(f"{path!r}: cannot index into {type(cur).__name__} at {part!r}")
    return cur


_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "contains": lambda a, b: b in a,
    "not_contains": lambda a, b: b not in a,
}


def _resolve(value: Any, saved: dict[str, Any]) -> Any:
    """ "$name" in a step's arguments is a value saved by an earlier step."""
    if isinstance(value, str) and value.startswith("$"):
        return saved[value[1:]]
    if isinstance(value, dict):
        return {k: _resolve(v, saved) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, saved) for v in value]
    return value


def _call(
    client: httpx2.Client,
    url: str,
    headers: dict[str, str],
    tool: str,
    args: dict[str, Any],
    expect_error: bool = False,
):
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}}
    r = client.post(url, headers=headers, json=body)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    result = r.json().get("result", {})
    if expect_error:  # a refusal is the expected answer: it must be an isError result, and say so in words
        if not result.get("isError"):
            return None, f"expected a refusal (isError), got {result.get('structuredContent')}"
        return {"error_text": " ".join(c.get("text", "") for c in result.get("content", []))}, ""
    if result.get("isError"):
        return None, f"tool returned isError: {result.get('content')}"
    return result.get("structuredContent", {}), ""


def _plan_step(step: dict[str, Any], saved: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    """The tool and arguments of a step. ``tool``/``args`` are used as written. ``say`` is a farmer's sentence sent
    through the Simulator's own intent rules (the host side of tool selection, no model): it must pick the tool the
    step names, and the matched arguments are what is sent. ``answer_word`` (haan, avunu, nahi, vaddu...) is turned
    into the yes/no ``answer`` by the same rules."""
    args = _resolve(step.get("args", {}), saved)
    tool = step.get("tool", "")
    if "say" in step:
        intent = match_intent(step["say"])
        if intent is None:
            return "", {}, f"nothing matched {step['say']!r}"
        if tool and intent.tool != tool:
            return "", {}, f"{step['say']!r} picked {intent.tool}, expected {tool}"
        tool, args = intent.tool, {**intent.arguments, **args}
    if "answer_word" in step:
        word = yes_no(step["answer_word"])
        if word is None:
            return "", {}, f"{step['answer_word']!r} is not a yes or a no"
        args = {**args, "answer": word}
    return tool, args, ""


def _check_case(
    client: httpx2.Client, url: str, headers: dict[str, str], case: dict[str, Any], clock: DemoClock
) -> tuple[bool, str]:
    """A case is one call (``tool``/``args``/``checks``) or ordered ``steps`` on one session. A step may first move
    the demo clock (``demo_days_later``: days after the real today, in process), say a sentence (``say``), turn a
    spoken yes/no into the answer (``answer_word``), or expect a refusal (``expect_error``)."""
    steps = case.get("steps") or [{"tool": case["tool"], "args": case["args"], "checks": case["checks"]}]
    saved: dict[str, Any] = {}
    for n, step in enumerate(steps, 1):
        unknown = sorted(set(step) - STEP_KEYS)
        if unknown:  # a typo in a case must fail it, never be skipped
            return False, f"step {n}: unknown key(s) {unknown}"
        if "demo_days_later" in step:
            clock.set_days_later(step["demo_days_later"])
        tool, args, problem = _plan_step(step, saved)
        where = f"step {n} ({tool or step.get('tool', '?')}): " if len(steps) > 1 else ""
        if problem:
            return False, where + problem
        poll = step.get("poll_until")
        deadline = time.monotonic() + POLL_SECONDS
        while True:
            sc, error = _call(client, url, headers, tool, args, bool(step.get("expect_error")))
            if sc is None:
                return False, where + error
            if poll is None or _OPS[poll["op"]](_get(sc, poll["field"]), poll["value"]):
                break
            if time.monotonic() > deadline:
                return False, f"{where}{poll['field']} still {_get(sc, poll['field'])!r} after {POLL_SECONDS}s"
            time.sleep(0.1)
        for check in step.get("checks", []):
            try:
                actual = _get(sc, check["field"])
            except (KeyError, IndexError, TypeError) as exc:
                return False, f"{where}{check['field']}: {exc}"
            if not _OPS[check["op"]](actual, check["value"]):
                return False, f"{where}{check['field']} {check['op']} {check['value']!r}: actual {actual!r}"
        for name, field in step.get("save", {}).items():
            saved[name] = _get(sc, field)
    return True, ""


def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    results: dict[str, tuple[bool, str]] = {}

    # One fresh server per model fixture (None = the demo rules), so fixture cases never share state. A case marked
    # ``fresh_state`` gets a server of its own: its answer must not depend on what earlier cases changed.
    def group(case: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
        weather = json.dumps(case["weather"], sort_keys=True) if "weather" in case else None  # its own server
        deaths = json.dumps(case["deaths_rule"], sort_keys=True) if "deaths_rule" in case else None
        return case.get("model_fixture"), case["id"] if case.get("fresh_state") else None, weather, deaths

    for fixture, only, weather, deaths in dict.fromkeys(group(c) for c in cases):
        port = _free_port()
        stop, clock = _serve(port, fixture, weather, deaths)
        try:
            with httpx2.Client(timeout=10) as client:
                url = f"http://127.0.0.1:{port}{MCP_PATH}"
                headers = _session(client, url)
                for case in (c for c in cases if group(c) == (fixture, only, weather, deaths)):
                    results[case["id"]] = _check_case(client, url, headers, case, clock)
        finally:
            stop()
    rows: list[tuple[str, bool, str]] = [(c["id"], *results[c["id"]]) for c in cases]

    passed = sum(1 for _, ok, _ in rows if ok)
    print()
    for cid, ok, detail in rows:
        print(f"  {'PASS' if ok else 'FAIL'}  {cid}" + (f"  ({detail})" if detail else ""))
    print(f"\neval-fast: {passed}/{len(rows)} golden cases passed (mock mode, no AWS)")

    EVALS_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Golden eval results (v0)",
        "",
        f"Run {datetime.now().astimezone().isoformat(timespec='seconds')}, mock mode (`MOCK_BEDROCK=true`), "
        f"no AWS. `python tasks.py eval-fast`. Fault cases (model fixture) run against a test model that answers "
        f"'routine' to everything or always fails (tests/fakes.py). Extended to the full suite later.",
        "",
        "| Case | Result | Detail |",
        "|---|---|---|",
    ]
    for cid, ok, detail in rows:
        lines.append(f"| {cid} | {'PASS' if ok else 'FAIL'} | {detail or '—'} |")
    lines.append("")
    lines.append(f"**Score: {passed}/{len(rows)}**")
    EVALS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"eval-fast: wrote {EVALS_MD.relative_to(ROOT).as_posix()}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
