"""Run one CluckTalk instance for systemd: the MCP server and the Simulator, together (Step 51 part E).

Both processes read the same environment (the unit's EnvironmentFile). If either one stops, the other is stopped
too and this exits non-zero, so systemd restarts the pair; a half-running instance is never left behind.
SIGTERM / Ctrl+C stops both. This starts nothing but those two modules and reads no setting itself: every refusal
(a missing token, a state file that is not the instance's own, a bad farm file) comes from the modules and stops the
start with their message.

    python scripts/run_instance.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ("clucktalk.server", "clucktalk.simulator")
GRACE_SECONDS = 10


def failure_code(returncode: int | None) -> int:
    """One child stopped on its own: that is a failure for the pair, even when it exited with 0."""
    return returncode or 1


def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env.get("PYTHONPATH", "")]))
    env.setdefault("PYTHONUNBUFFERED", "1")
    procs = [subprocess.Popen([sys.executable, "-m", module], cwd=ROOT, env=env) for module in MODULES]
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(getattr(signal, "SIGTERM", signal.SIGINT), stop)
    code = 0
    while not stopping:
        exited = [p for p in procs if p.poll() is not None]
        if exited:
            code = failure_code(exited[0].returncode)
            break
        time.sleep(0.5)
    for p in procs:
        if p.poll() is None:
            p.terminate()
    deadline = time.monotonic() + GRACE_SECONDS
    for p in procs:
        try:
            p.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            p.kill()
    return code


if __name__ == "__main__":
    sys.exit(main())
