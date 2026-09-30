"""Latency report: p50 / p95 / max per MCP call and per Simulator turn, measured over real localhost HTTP.

Starts its own MCP server and Simulator (demo data) on free 127.0.0.1 ports, warms up, then times each call.
Budget (docs/DESIGN.md §3, Amazon Alexa+ guidance): every MCP round trip under 500 ms.

Usage (Windows):
    <venv python> scripts/latency_report.py            print a Markdown table
    <venv python> scripts/latency_report.py -n 200     more samples per row
"""

from __future__ import annotations

import argparse
import platform
import socket
import statistics
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import httpx2  # noqa: E402
import uvicorn  # noqa: E402

from clucktalk.config import load_settings  # noqa: E402
from clucktalk.server.app import MCP_PATH, TARGET_PROTOCOL_VERSION, build_app  # noqa: E402
from clucktalk.server.cards import FARM_STATUS_URI  # noqa: E402
from clucktalk.simulator.app import SimulatorSettings  # noqa: E402
from clucktalk.simulator.app import build_app as build_simulator  # noqa: E402

BUDGET_MS = 500
HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(app, port: int) -> Callable[[], None]:
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not uv.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise SystemExit("server did not start")
        time.sleep(0.02)

    def stop() -> None:
        uv.should_exit = True
        thread.join(timeout=10)

    return stop


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
                "clientInfo": {"name": "latency", "version": "0"},
            },
        },
    )
    h = {**HEADERS, "mcp-session-id": r.headers["mcp-session-id"], "mcp-protocol-version": TARGET_PROTOCOL_VERSION}
    client.post(url, headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return h


def _time(fn: Callable[[], None], n: int, warmup: int = 5) -> list[float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return samples


def _row(name: str, samples: list[float]) -> str:
    q = statistics.quantiles(samples, n=100, method="inclusive")
    p50, p95, worst = q[49], q[94], max(samples)
    verdict = "within budget" if p95 < BUDGET_MS else "OVER BUDGET"
    return f"| {name} | {len(samples)} | {p50:.1f} | {p95:.1f} | {worst:.1f} | {verdict} |"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", type=int, default=100, help="samples per row (default 100)")
    n = parser.parse_args().n

    mcp_port, sim_port = _free_port(), _free_port()
    settings = load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_PORT": str(mcp_port)})
    stops = [_serve(build_app(settings), mcp_port)]
    url = f"http://127.0.0.1:{mcp_port}{MCP_PATH}"
    stops.append(_serve(build_simulator(SimulatorSettings(port=sim_port, mcp_url=url, auth_token=None)), sim_port))
    rows = []
    try:
        with httpx2.Client(timeout=15) as client:
            h = _session(client, url)
            rid = iter(range(10, 10**9))

            def call(method: str, params: dict, expect_error: bool = False) -> Callable[[], None]:
                def go() -> None:
                    r = client.post(
                        url, headers=h, json={"jsonrpc": "2.0", "id": next(rid), "method": method, "params": params}
                    )
                    body = r.json()
                    if r.status_code != 200 or "result" not in body:
                        raise SystemExit(f"{method} failed: {r.status_code} {body}")
                    if bool(body["result"].get("isError")) != expect_error:  # a timed call must be the intended one
                        raise SystemExit(
                            f"{method} {params}: isError={body['result'].get('isError')}, expected {expect_error}"
                        )

                return go

            def tool(name: str, args: dict, expect_error: bool = False) -> Callable[[], None]:
                return call("tools/call", {"name": name, "arguments": args}, expect_error)

            measured = [
                ("tools/call get_farm_status (whole farm)", tool("get_farm_status", {})),
                ("tools/call get_farm_status (shed two)", tool("get_farm_status", {"house": "shed two"})),
                (
                    "tools/call get_farm_status (unknown shed: error path)",
                    tool("get_farm_status", {"house": "shed nine"}, expect_error=True),
                ),
                ("tools/call plan_feed (shed two)", tool("plan_feed", {"house": "shed two"})),
                ("tools/call plan_feed (whole farm)", tool("plan_feed", {})),
                ("tools/call get_help", tool("get_help", {})),
                ("tools/call get_farm_profile", tool("get_farm_profile", {})),
                # Each call supersedes the previous proposal and stores a new one: the write path's heavy case.
                (
                    "tools/call set_farm_mode (propose: 2 writes + read-back)",
                    tool("set_farm_mode", {"mode": "contract"}),
                ),
                ("resources/read farm-status card (~385 KB)", call("resources/read", {"uri": FARM_STATUS_URI})),
            ]
            for name, fn in measured:
                rows.append(_row(name, _time(fn, n)))

            sim_origin = f"http://127.0.0.1:{sim_port}"

            def turn(utterance: str) -> Callable[[], None]:
                def go() -> None:
                    r = client.post(
                        sim_origin + "/api/turn",
                        headers={"origin": sim_origin},
                        json={"utterance": utterance, "device": "show"},
                    )
                    if r.status_code != 200 or r.json().get("kind") != "tool":
                        raise SystemExit(f"turn failed: {r.status_code} {r.text[:200]}")

                return go

            rows.append(
                _row(
                    "Simulator turn: text -> rule -> tools/call -> answer (backend)",
                    _time(turn("How is shed two doing?"), n),
                )
            )
    finally:
        for stop in reversed(stops):
            stop()

    print(
        f"Latency report, {datetime.now().isoformat(timespec='seconds')}, {platform.system()} {platform.release()}, "
        f"Python {platform.python_version()}, demo data, localhost HTTP "
        f"(Streamable HTTP, protocol {TARGET_PROTOCOL_VERSION})\n"
    )
    print("| Call | n | p50 ms | p95 ms | max ms | Budget (p95 < 500 ms) |")
    print("|---|---|---|---|---|---|")
    print("\n".join(rows))
    print("\nLocal loopback only: no network, TLS, or cloud hop. Browser rendering and speech are not included.")
    return 0 if all("OVER" not in r for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
