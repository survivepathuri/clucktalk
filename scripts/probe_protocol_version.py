"""Probe which MCP protocol version the server answers with, for each version a client might ask for.

Starts the server (mock mode, no AWS) on a TEMPORARY state file and a free port, sends one ``initialize`` request per
version, prints a table, and stops the server. The live farm state file is never opened, whatever the environment says.
Exit code: 0 when the table was printed, 1 when the server did not start or a request failed.

Usage (Windows):  python tasks.py probe-protocol-version
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import httpx2  # noqa: E402

from clucktalk.server.app import MCP_PATH  # noqa: E402

VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
HEADER = ("Requested", "HTTP status", "Server answered with")
# Settings that would send the probe to the live state, a clock, a token or live AI: the probe sets its own.
DROPPED_ENV = ("CLUCKTALK_STATE_PATH", "CLUCKTALK_DEMO_DAYS_LATER", "CLUCKTALK_AUTH_TOKEN", "CLUCKTALK_ALLOWED_ORIGINS")


def format_table(rows: Sequence[tuple[str, int, str | None]]) -> str:
    cells = [HEADER, *((requested, str(status), answered or "-") for requested, status, answered in rows)]
    widths = [max(len(row[i]) for row in cells) for i in range(3)]

    def line(row: Sequence[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()

    return "\n".join([line(cells[0]), "-+-".join("-" * w for w in widths), *(line(r) for r in cells[1:])])


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, proc: subprocess.Popen, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


def _initialize(url: str, version: str) -> tuple[int, str | None]:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "probe", "version": "0"}},
    }
    r = httpx2.post(
        url,
        json=body,
        headers={"content-type": "application/json", "accept": "application/json, text/event-stream"},
        timeout=10,
    )
    answered = None
    if r.status_code == 200:
        answered = r.json().get("result", {}).get("protocolVersion")
        if sid := r.headers.get("mcp-session-id"):
            httpx2.delete(url, headers={"mcp-session-id": sid, "mcp-protocol-version": answered or version}, timeout=10)
    return r.status_code, answered


def _stop(proc: subprocess.Popen) -> None:
    """Stop the server and everything it started. On Windows the venv's python.exe is a launcher that starts the real
    interpreter as a child, so ending only the launcher would leave the server running."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
    elif proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def main(server_command: Sequence[str] | None = None, start_seconds: float = 20) -> int:
    port = _free_port()
    url = f"http://127.0.0.1:{port}{MCP_PATH}"
    command = list(server_command or [sys.executable, "-B", "-m", "clucktalk.server"])
    tmp = Path(tempfile.mkdtemp(prefix="clucktalk_probe_"))
    state = tmp / "probe.sqlite3"
    log = tmp / "server.log"
    env = {k: v for k, v in os.environ.items() if k not in DROPPED_ENV}
    env.update(
        MOCK_BEDROCK="true",
        CLUCKTALK_HOST="127.0.0.1",
        CLUCKTALK_PORT=str(port),
        CLUCKTALK_STATE_PATH=str(state),
        PYTHONPATH=str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", ""),
        PYTHONIOENCODING="utf-8",
    )
    print(f"Temporary state file: {state}")
    print(f"Server: {url}")
    proc: subprocess.Popen | None = None
    try:
        with log.open("wb") as out:
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
            started = _wait_for_port(port, proc, start_seconds)
        if not started:
            tail = log.read_text(encoding="utf-8", errors="replace").strip()[-1500:]
            print(f"probe-protocol-version: the server did not start on port {port}.\n{tail}", file=sys.stderr)
            return 1
        rows = []
        for version in VERSIONS:
            try:
                status, answered = _initialize(url, version)
            except httpx2.HTTPError as exc:
                print(f"probe-protocol-version: the request for {version} failed: {exc!r}", file=sys.stderr)
                return 1
            rows.append((version, status, answered))
        print()
        print(format_table(rows))
        return 0
    finally:
        if proc is not None:
            _stop(proc)
        shutil.rmtree(tmp)


if __name__ == "__main__":
    sys.exit(main())
