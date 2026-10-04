"""OUR replay of the flow documented on Amazon's Local Inspector page, against a local server. It is not Amazon's tool,
and the Local Inspector itself was not run (its install guide is behind a Developer Console login, FL-024).

Starts the server (mock mode, no AWS) on a TEMPORARY state file and a free port (the live farm state is never opened),
then replays, with ``Accept: application/json`` ONLY as in the documented example: ``initialize`` with protocolVersion
2025-06-18 and clientInfo ``addon-local-inspector``, ``notifications/initialized``, ``tools/list``, ``resources/read``
for every ui:// resource, and ``tools/call`` for every tool with schema-valid arguments from a small fixture. Prints one
table for the first round (step, HTTP status, ok or not, milliseconds) and the p50 and p95 per step over all rounds.

Exit code: 0 when every step of every round was ok, 1 otherwise or when the server did not start.

Usage (Windows):  python tasks.py inspector-replay
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import httpx2  # noqa: E402
import probe_protocol_version as probe  # noqa: E402  (the server start and stop helpers)

from clucktalk.server.app import MCP_PATH  # noqa: E402

DOCUMENTED_PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "addon-local-inspector"
ROUNDS = 20
BUDGET_MS = 500  # docs/DESIGN.md: every tool returns in under 500 ms (p95)
DISCLAIMER = (
    "This is OUR replay of the flow documented on Amazon's Local Inspector page. It is not Amazon's tool, and the "
    "Local Inspector itself was not run (FL-024)."
)

# Schema-valid arguments for every tool. A call that would change data only proposes it (needs_confirmation), and the
# ones that need a stored check answer with a structured error: the replay judges the protocol answer, not the farm.
TOOL_ARGUMENTS: dict[str, dict] = {
    "get_help": {},
    "get_farm_status": {},
    "get_daily_briefing": {},
    "get_farm_profile": {},
    "get_record_book": {},
    "plan_feed": {"house": "shed 1"},
    "plan_sale": {"house": "shed 1"},
    "start_health_check": {"house": "shed 1", "signs": ["coughing"]},
    "get_health_check": {},
    "set_farm_mode": {"mode": "contract"},
    "set_contract_terms": {
        "base_rate_per_kg": 6.5,
        "standard_fcr": 1.65,
        "incentive_per_kg_per_fcr_point": 0.2,
        "deduction_per_kg_per_fcr_point": 0.2,
    },
    "log_daily_record": {"house": "shed 1", "deaths": 1},
    "prepare_vet_handoff": {"house": "shed 2"},
    "report_health_follow_up": {"house": "shed 1", "outcome": "same"},
}


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100) of a non-empty list."""
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def format_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    cells = [tuple(header), *(tuple(r) for r in rows)]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]

    def line(row: Sequence[str]) -> str:
        return " | ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip()

    return "\n".join([line(cells[0]), "-+-".join("-" * w for w in widths), *(line(r) for r in cells[1:])])


class Replay:
    """One session replaying the documented flow. Each ``step`` returns (name, HTTP status, ok, milliseconds)."""

    def __init__(self, url: str, timeout: float = 30) -> None:
        self.url = url
        self.http = httpx2.Client(timeout=timeout)
        self.session_id: str | None = None
        self.protocol_version = DOCUMENTED_PROTOCOL_VERSION
        self._next_id = 1
        self.accept_json_only_ok: bool | None = None

    def close(self) -> None:
        if self.session_id:
            self.http.delete(self.url, headers=self._headers(), timeout=10)
        self.http.close()

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json", "accept": "application/json"}  # JSON only, as documented
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
            headers["mcp-protocol-version"] = self.protocol_version
        return headers

    def _send(
        self, name: str, body: dict, ok: Callable[[httpx2.Response, dict | None], bool]
    ) -> tuple[tuple, dict | None]:
        started = time.perf_counter()
        r = self.http.post(self.url, json=body, headers=self._headers())
        ms = (time.perf_counter() - started) * 1000
        payload = None
        if r.content:
            try:
                payload = r.json()
            except ValueError:
                payload = None
        return (name, r.status_code, ok(r, payload), ms), payload

    def _request(self, name: str, method: str, params: dict | None = None) -> tuple[tuple, dict | None]:
        body: dict = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        self._next_id += 1
        if params is not None:
            body["params"] = params

        def ok(r: httpx2.Response, payload: dict | None) -> bool:
            return (
                r.status_code == 200
                and r.headers.get("content-type", "").startswith("application/json")
                and isinstance(payload, dict)
                and "result" in payload
                and "error" not in payload
            )

        return self._send(name, body, ok)

    def initialize_and_keep_session(self) -> tuple:
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": DOCUMENTED_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": "1.0.0"},
            },
        }
        self._next_id += 1
        started = time.perf_counter()
        r = self.http.post(self.url, json=body, headers=self._headers())
        ms = (time.perf_counter() - started) * 1000
        try:
            payload = r.json() if r.status_code == 200 and r.content else None
        except ValueError:  # an event stream or other text: the step is then reported as not ok
            payload = None
        self.session_id = r.headers.get("mcp-session-id")
        answered = (payload or {}).get("result", {}).get("protocolVersion")
        if answered:
            self.protocol_version = answered
        ok = (
            r.status_code == 200
            and r.headers.get("content-type", "").startswith("application/json")
            and answered is not None
            and self.session_id is not None
        )
        self.accept_json_only_ok = ok
        return "initialize", r.status_code, ok, ms

    def initialized(self) -> tuple:
        body = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        return self._send("notifications/initialized", body, lambda r, p: r.status_code == 202)[0]

    def tools_list(self) -> tuple[tuple, list[dict]]:
        step, payload = self._request("tools/list", "tools/list")
        return step, ((payload or {}).get("result") or {}).get("tools", [])

    def resource_uris(self) -> list[str]:
        _step, payload = self._request("resources/list", "resources/list")
        return [
            x["uri"] for x in ((payload or {}).get("result") or {}).get("resources", []) if x["uri"].startswith("ui://")
        ]

    def read_resource(self, uri: str) -> tuple:
        return self._request(f"resources/read {uri}", "resources/read", {"uri": uri})[0]

    def call_tool(self, name: str, arguments: dict) -> tuple:
        return self._request(f"tools/call {name}", "tools/call", {"name": name, "arguments": arguments})[0]


def run_round(url: str) -> list[tuple]:
    """One full replay on a fresh session. Returns the steps in order."""
    replay = Replay(url)
    steps: list[tuple] = []
    try:
        steps.append(replay.initialize_and_keep_session())
        steps.append(replay.initialized())
        listed, tools = replay.tools_list()
        steps.append(listed)
        for uri in replay.resource_uris():
            steps.append(replay.read_resource(uri))
        for tool in tools:
            name = tool["name"]
            steps.append(replay.call_tool(name, TOOL_ARGUMENTS[name]))
    finally:
        replay.close()
    return steps


def summarize(rounds: Sequence[Sequence[tuple]]) -> list[tuple[str, float, float, float, bool]]:
    """(step, p50, p95, max, all ok) per step name over all rounds."""
    by_step: dict[str, list[float]] = {}
    ok: dict[str, bool] = {}
    for steps in rounds:
        for name, _status, good, ms in steps:
            by_step.setdefault(name, []).append(ms)
            ok[name] = ok.get(name, True) and good
    return [(n, percentile(v, 50), percentile(v, 95), max(v), ok[n]) for n, v in by_step.items()]


@contextmanager
def running_server(start_seconds: float = 20) -> Iterator[str]:
    """The server on a temporary state file and a free port, stopped and deleted afterwards. Raises RuntimeError when it
    does not start."""
    import os
    import subprocess

    port = probe._free_port()
    url = f"http://127.0.0.1:{port}{MCP_PATH}"
    tmp = Path(tempfile.mkdtemp(prefix="clucktalk_replay_"))
    env = {k: v for k, v in os.environ.items() if k not in probe.DROPPED_ENV}
    env.update(
        MOCK_BEDROCK="true",
        CLUCKTALK_HOST="127.0.0.1",
        CLUCKTALK_PORT=str(port),
        CLUCKTALK_STATE_PATH=str(tmp / "replay.sqlite3"),
        PYTHONPATH=str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", ""),
        PYTHONIOENCODING="utf-8",
    )
    log = tmp / "server.log"
    proc = None
    try:
        with log.open("wb") as out:
            proc = subprocess.Popen(
                [sys.executable, "-B", "-m", "clucktalk.server"],
                cwd=ROOT,
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
            started = probe._wait_for_port(port, proc, start_seconds)
        if not started:
            raise RuntimeError(f"the server did not start on port {port}: {log.read_text(errors='replace')[-800:]}")
        yield url
    finally:
        if proc is not None:
            probe._stop(proc)
        shutil.rmtree(tmp, ignore_errors=True)


def collect(url: str, rounds: int = ROUNDS) -> list[list[tuple]]:
    run_round(url)  # one warm-up round, not counted (imports, first request)
    return [run_round(url) for _ in range(rounds)]


def main(rounds: int = ROUNDS) -> int:
    print(DISCLAIMER)
    try:
        with running_server() as url:
            print(f"Server: {url} (temporary state file, mock mode, no AWS)")
            print(
                "Request headers: Accept: application/json ONLY; protocolVersion 2025-06-18; client "
                "addon-local-inspector"
            )
            all_rounds = collect(url, rounds)
    except (RuntimeError, httpx2.HTTPError) as exc:
        print(f"inspector-replay: {exc}", file=sys.stderr)
        return 1
    print(f"\nFirst round (of {rounds}):")
    print(
        format_table(
            ("step", "HTTP", "ok", "ms"),
            [(n, str(s), "ok" if g else "NOT OK", f"{ms:.1f}") for n, s, g, ms in all_rounds[0]],
        )
    )
    summary = summarize(all_rounds)
    print(f"\np50 and p95 per step over {rounds} rounds (milliseconds; the budget is {BUDGET_MS} ms at p95):")
    print(
        format_table(
            ("step", "p50", "p95", "max", "all ok"),
            [(n, f"{a:.1f}", f"{b:.1f}", f"{m:.1f}", "yes" if g else "NO") for n, a, b, m, g in summary],
        )
    )
    accept_ok = all(r[0][3] is not None and r[0][2] for r in all_rounds)
    print(
        f"\nAccept: application/json only handled correctly (JSON answer, session id, 202 for the notification): "
        f"{'yes' if accept_ok else 'NO'}"
    )
    bad = [n for n, _a, _b, _m, g in summary if not g]
    over = [n for n, _a, b, _m, _g in summary if b >= BUDGET_MS]
    print(
        f"Steps not ok: {', '.join(bad) if bad else 'none'}. Steps with p95 at or over {BUDGET_MS} ms: "
        f"{', '.join(over) if over else 'none'}."
    )
    print("\n" + DISCLAIMER)
    print(json.dumps({"replay_summary": {n: {"p50": round(a, 1), "p95": round(b, 1)} for n, a, b, _m, _g in summary}}))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
