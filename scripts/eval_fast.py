"""Golden eval suite v0 (mock mode, no AWS): runs data/eval/golden_cases.json against a real MCP server over
real HTTP, prints a pass/fail table, and writes docs/EVALS.md. Extended to the full suite on the 11 Oct task
(private/WEEK2_PLAN.md); this file exists to make `python tasks.py eval-fast` real rather than "not implemented".

Never invents a score: every row is a real HTTP round trip against the same MCP server `tasks.py serve` runs
(CLAUDE.md Rule 5, Rule 6). The demo farm is date-relative, so results do not depend on which day this runs.

Usage (Windows):
    .venv\\Scripts\\python scripts\\eval_fast.py
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import httpx2  # noqa: E402
import uvicorn  # noqa: E402

from clucktalk.config import load_settings  # noqa: E402
from clucktalk.server.app import MCP_PATH, TARGET_PROTOCOL_VERSION, build_app  # noqa: E402

CASES_PATH = ROOT / "data" / "eval" / "golden_cases.json"
EVALS_MD = ROOT / "docs" / "EVALS.md"
HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(port: int):
    settings = load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_PORT": str(port)})
    uv = uvicorn.Server(uvicorn.Config(build_app(settings), host="127.0.0.1", port=port, log_level="warning"))
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


def _check_case(client: httpx2.Client, url: str, headers: dict[str, str], case: dict[str, Any]) -> tuple[bool, str]:
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": case["tool"], "arguments": case["args"]},
    }
    r = client.post(url, headers=headers, json=body)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    result = r.json().get("result", {})
    if result.get("isError"):
        return False, f"tool returned isError: {result.get('content')}"
    sc = result.get("structuredContent", {})
    for check in case["checks"]:
        try:
            actual = _get(sc, check["field"])
        except (KeyError, IndexError, TypeError) as exc:
            return False, f"{check['field']}: {exc}"
        if not _OPS[check["op"]](actual, check["value"]):
            return False, f"{check['field']} {check['op']} {check['value']!r}: actual {actual!r}"
    return True, ""


def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    port = _free_port()
    stop = _serve(port)
    rows: list[tuple[str, bool, str]] = []
    try:
        with httpx2.Client(timeout=10) as client:
            url = f"http://127.0.0.1:{port}{MCP_PATH}"
            headers = _session(client, url)
            for case in cases:
                ok, detail = _check_case(client, url, headers, case)
                rows.append((case["id"], ok, detail))
    finally:
        stop()

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
        f"no AWS. `python tasks.py eval-fast`. Extended to the full 45-case suite on the 11 Oct task.",
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
