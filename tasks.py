"""CluckTalk task runner: one cross-platform entry point, standard library only (CLAUDE.md Rule 12).

Windows (cmd); on Linux/macOS use python3 instead of python:
    python tasks.py setup       Create .venv with Python 3.12 or 3.13 and install pinned deps
    python tasks.py check       Lint + unit + contract tests + AOSS check + secret scan (Rule 3)
    python tasks.py eval-fast   Golden eval suite in mock mode, no AWS needed
    python tasks.py serve       Start only the MCP server (demo data, http://127.0.0.1:8765/mcp)
    python tasks.py run         Start the local demo (Simulator + MCP server, mock mode)
    python tasks.py serve --demo-days-later 3   (also for run) demo clock: "today" is 3 days later; demo mode only
    python tasks.py demo-three-days   Build the demo-clock state for the "three days later" recording (demo mode only)
    python tasks.py probe-protocol-version   Print which MCP protocol version a temporary server answers with
    python tasks.py reset-demo --yes   Reset the local farm state (.local/): the live file is MOVED to .local/backups,
                                       the demo-clock file is deleted. Without --yes it only lists what it would do

Every step prints PASS / FAIL / SKIP, and the run exits non-zero if any step fails.
A skipped step is always shown with its reason. Nothing is silently skipped (Rule 6).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

SUPPORTED_PYTHONS = ((3, 12), (3, 13))  # the tested versions (CI targets)
MIN_PYTHON = (3, 11)  # below this: refuse; between MIN_PYTHON and the next untested version: warn and continue
SUPPORTED_STR = " or ".join(f"{major}.{minor}" for major, minor in SUPPORTED_PYTHONS)
INSTALL_HINT = (
    f"Install Python {SUPPORTED_STR}: python.org (Windows/macOS), 'brew install python@3.13' (macOS), "
    "'pyenv install 3.13', or the deadsnakes PPA (Ubuntu)."
)
ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
DEV_REQUIREMENTS = ROOT / "requirements-dev.txt"
APP_REQUIREMENTS = ROOT / "requirements.txt"
PYTEST_NO_TESTS_COLLECTED = 5


def python_support(version: tuple[int, int]) -> str:
    """'supported' (tested), 'untested' (warn, continue; pip fails loudly if a wheel is missing) or 'too_old'."""
    if tuple(version[:2]) in SUPPORTED_PYTHONS:
        return "supported"
    return "untested" if tuple(version[:2]) >= MIN_PYTHON else "too_old"


def _warn_untested(version: tuple[int, int], what: str) -> None:
    print(
        f"WARNING: untested Python version {version[0]}.{version[1]} ({what}). "
        f"Tested: {SUPPORTED_STR}. Continuing; if a pinned package has no wheel for it, pip will fail loudly.",
        flush=True,
    )


def format_hint() -> str:
    return f"run: {VENV_PY.relative_to(ROOT)} -m ruff format ."


def _run(cmd: list[str | Path]) -> int:
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    return subprocess.call([str(c) for c in cmd], cwd=ROOT)


def _venv_python_version() -> tuple[int, int] | None:
    if not VENV_PY.exists():
        return None
    out = subprocess.run(
        [str(VENV_PY), "-c", "import sys; print(*sys.version_info[:2])"], capture_output=True, text=True, check=True
    )
    major, minor = out.stdout.split()
    return int(major), int(minor)


def _base_python() -> list[str]:
    """Command that starts a supported Python (3.12/3.13); otherwise the current one if >= 3.11, with a warning."""
    here = sys.version_info[:2]
    support = python_support(here)
    if support == "supported":
        return [sys.executable]
    launcher = shutil.which("py")
    for major, minor in reversed(SUPPORTED_PYTHONS):
        if launcher and subprocess.call([launcher, f"-{major}.{minor}", "-c", ""], stderr=subprocess.DEVNULL) == 0:
            return [launcher, f"-{major}.{minor}"]
        unix_name = shutil.which(f"python{major}.{minor}")
        if unix_name:
            return [unix_name]
    if support == "untested":
        _warn_untested(here, "no Python 3.12 or 3.13 found, using the one running tasks.py")
        return [sys.executable]
    sys.exit(
        f"ERROR: Python {here[0]}.{here[1]} is too old (need {SUPPORTED_STR}; 3.11+ runs with a warning). "
        + INSTALL_HINT
    )


def _require_venv() -> None:
    version = _venv_python_version()
    if version is None:
        sys.exit("ERROR: .venv not found. Run 'python tasks.py setup' first (python3 on Linux/macOS).")
    support = python_support(version)
    if support == "too_old":
        sys.exit(
            f"ERROR: .venv uses Python {version[0]}.{version[1]}, project needs {SUPPORTED_STR}. "
            "Run 'python tasks.py setup' to recreate it."
        )
    if support == "untested":
        _warn_untested(version, ".venv")


def setup() -> int:
    version = _venv_python_version()
    if version is not None and python_support(version) == "too_old":
        print(f"Existing .venv uses Python {version[0]}.{version[1]}; recreating it ...")
        shutil.rmtree(VENV)
    if not VENV_PY.exists():
        base = _base_python()
        print(f"Creating virtual environment in {VENV} with: {' '.join(base)}")
        code = _run([*base, "-m", "venv", VENV])
        if code != 0:
            print(f"setup: FAILED creating .venv (exit {code})")
            return code
    code = _run([VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", DEV_REQUIREMENTS])
    if code == 0 and APP_REQUIREMENTS.exists():
        code = _run([VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", APP_REQUIREMENTS])
    print("setup: OK" if code == 0 else f"setup: FAILED (exit {code})")
    return code


def _pytest_step(label: str, test_dir: str) -> tuple[str, str]:
    if not (ROOT / test_dir).is_dir():
        return "SKIP", f"{test_dir}/ does not exist yet"
    code = _run([VENV_PY, "-m", "pytest", "-q", test_dir])
    if code == 0:
        return "PASS", ""
    if code == PYTEST_NO_TESTS_COLLECTED:
        return "SKIP", f"no {label} tests collected in {test_dir}/"
    return "FAIL", f"pytest exit {code}"


def check() -> int:
    _require_venv()
    steps: list[tuple[str, Callable[[], tuple[str, str]]]] = [
        ("lint (ruff)", lambda: ("PASS", "") if _run([VENV_PY, "-m", "ruff", "check", "."]) == 0 else ("FAIL", "")),
        (
            "format (ruff)",
            lambda: (
                ("PASS", "")
                if _run([VENV_PY, "-m", "ruff", "format", "--check", "."]) == 0
                else ("FAIL", format_hint())
            ),
        ),
        ("harness tests", lambda: _pytest_step("harness", "tests/harness")),
        ("unit tests", lambda: _pytest_step("unit", "tests/unit")),
        ("contract tests", lambda: _pytest_step("contract", "tests/contract")),
        ("AOSS check", lambda: ("PASS", "") if _run([VENV_PY, "scripts/check_no_aoss.py"]) == 0 else ("FAIL", "")),
        ("secret scan", lambda: ("PASS", "") if _run([VENV_PY, "scripts/scan_secrets.py"]) == 0 else ("FAIL", "")),
    ]
    results = []
    for name, step in steps:
        print(f"\n== {name} ==", flush=True)
        results.append((name, *step()))

    print("\n== check summary ==")
    for name, status, note in results:
        print(f"  {status:<4}  {name}" + (f"  ({note})" if note else ""))
    failed = [r for r in results if r[1] == "FAIL"]
    skipped = [r for r in results if r[1] == "SKIP"]
    if failed:
        print(f"check: FAILED ({len(failed)} step(s))")
        return 1
    print("check: PASSED" + (f" with {len(skipped)} skipped step(s) - see above" if skipped else ""))
    return 0


def _demo_env(command: str) -> dict[str, str]:
    """Demo mode is switched on here, explicitly and visibly (Rule 6)."""
    env = dict(os.environ)
    if env.get("MOCK_BEDROCK", "").strip() == "":
        env["MOCK_BEDROCK"] = "true"
        print(f"{command}: MOCK_BEDROCK not set, so starting in DEMO DATA mode (MOCK_BEDROCK=true).", flush=True)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


def serve() -> int:
    """MCP server only."""
    _require_venv()
    env = _demo_env("serve")
    try:
        return subprocess.call([str(VENV_PY), "-m", "clucktalk.server"], cwd=ROOT, env=env)
    except KeyboardInterrupt:
        print("serve: stopped.")
        return 0


def eval_fast() -> int:
    """Golden eval suite (mock mode, no AWS): scripts/eval_fast.py."""
    _require_venv()
    return _run([VENV_PY, "-B", ROOT / "scripts" / "eval_fast.py"])


def demo_three_days() -> int:
    """Build the demo-clock state file by making the Session 4 MCP calls (scripts/demo_three_days.py)."""
    _require_venv()
    env = _demo_env("demo-three-days")
    return subprocess.call([str(VENV_PY), "-B", str(ROOT / "scripts" / "demo_three_days.py")], cwd=ROOT, env=env)


def probe_protocol_version() -> int:
    """Start the server on a temporary state file, send initialize for four protocol versions, print the answers."""
    _require_venv()
    return subprocess.call([str(VENV_PY), "-B", str(ROOT / "scripts" / "probe_protocol_version.py")], cwd=ROOT)


def _wait_for_port(port: int, proc: subprocess.Popen, seconds: float = 20) -> bool:
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


def run() -> int:
    """Local demo: MCP server + Simulator, demo data. Set CLUCKTALK_NO_BROWSER=1 to skip opening the browser."""
    _require_venv()
    env = _demo_env("run")
    mcp_port = int(env.get("CLUCKTALK_PORT") or 8765)
    sim_port = int(env.get("CLUCKTALK_SIMULATOR_PORT") or 8766)
    procs: list[subprocess.Popen] = []
    try:
        server = subprocess.Popen([str(VENV_PY), "-m", "clucktalk.server"], cwd=ROOT, env=env)
        procs.append(server)
        if not _wait_for_port(mcp_port, server):
            print(f"run: the MCP server did not start on port {mcp_port} (see the error above).", file=sys.stderr)
            return 1
        sim = subprocess.Popen([str(VENV_PY), "-m", "clucktalk.simulator"], cwd=ROOT, env=env)
        procs.append(sim)
        if not _wait_for_port(sim_port, sim):
            print(f"run: the Simulator did not start on port {sim_port} (see the error above).", file=sys.stderr)
            return 1
        url = f"http://127.0.0.1:{sim_port}/"
        print(f"\nrun: ready. Open {url}  (Ctrl+C to stop)\n", flush=True)
        if env.get("CLUCKTALK_NO_BROWSER", "").strip() not in ("1", "true"):
            webbrowser.open(url)
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        print("run: a process exited; stopping.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("run: stopped.")
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()


_COUNTED_TABLES = (  # what a farmer may have entered: shown before anything is touched
    ("records", "daily records"),
    ("health_checks", "health checks"),
    ("vet_handoffs", "vet handoffs"),
    ("proposals", "saved changes"),
    ("follow_up_answers", "follow-up answers"),
)


def _describe_state_file(path: Path) -> tuple[bool, str]:
    """(marked as a demo-clock file, a one-line description with the size and the record counts). Read-only: the file
    is opened with mode=ro, so looking at it can never change it."""
    import sqlite3

    size = f"{path.stat().st_size} bytes"
    try:
        db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            marked = db.execute("SELECT 1 FROM meta WHERE key = 'demo_clock'").fetchone() is not None
            counts = []
            for table, label in _COUNTED_TABLES:
                try:
                    counts.append(f"{db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]} {label}")
                except sqlite3.OperationalError:  # a table this schema version does not have
                    continue
        finally:
            db.close()
    except sqlite3.DatabaseError:
        return False, f"{size}, not a readable database"
    return marked, f"{size}, " + (", ".join(counts) if counts else "no record tables")


def reset_demo(args: list[str] | None = None) -> int:
    """Clear the local farm state so the demo tells its seeded story again, without destroying real data silently.

    Lists every file with its size and record counts first. Without ``--yes`` that is all it does. With ``--yes`` the
    demo-clock file (marked as such, holds only shifted demo dates) is deleted; any other state file is MOVED to a
    ``backups`` folder next to it with a timestamp, never deleted. There is no marker for a demo-seeded live file, so
    every unmarked file is treated as possibly real."""
    args = [] if args is None else args
    if args not in ([], ["--yes"]):
        print("reset-demo: the only option is --yes.", file=sys.stderr)
        print(__doc__)
        return 2
    sys.path.insert(0, str(ROOT / "src"))
    from clucktalk.config import ConfigError, load_settings  # stdlib-only module: safe outside the venv

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"reset-demo: configuration error: {exc}", file=sys.stderr)
        return 2
    # Both files: the live state and the demo clock's own (config accepts only .sqlite3 files, so nothing else can go).
    paths = (settings.state_path, settings.demo_clock_state_path)
    plan: list[tuple[Path, bool]] = []  # (state file, delete it: it is marked as a demo-clock file)
    for path in paths:
        if not path.exists():
            continue
        marked, description = _describe_state_file(path)
        plan.append((path, marked))
        what = "demo-clock file, will be deleted" if marked else f"will be MOVED to {path.parent / 'backups'}"
        print(f"reset-demo: {path}: {description} ({what})")
    if not plan:
        print(f"reset-demo: nothing to reset ({paths[0]} and {paths[1]} do not exist).")
        return 0
    if args != ["--yes"]:
        print(
            "reset-demo: nothing was changed. Run it again with --yes to do this: python tasks.py reset-demo --yes",
            file=sys.stderr,
        )
        return 2
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for path, delete in plan:
        for target in (path, path.with_name(path.name + "-journal")):
            if not target.exists():
                continue
            try:
                if delete:
                    target.unlink()
                    print(f"reset-demo: deleted {target}")
                else:
                    kept = _backup_name(target, stamp)
                    kept.parent.mkdir(exist_ok=True)
                    target.rename(kept)
                    print(f"reset-demo: moved {target} to {kept}")
            except PermissionError:
                print(
                    f"reset-demo: {target} is in use. Stop the running demo (Ctrl+C), then run reset-demo again.",
                    file=sys.stderr,
                )
                return 1
    print("reset-demo: done. The next start tells the seeded demo story (independent farm).")
    return 0


def _backup_name(target: Path, stamp: str) -> Path:
    """backups/<name>.<timestamp><suffix>, never an existing file (a second reset in one second gets a counter)."""
    base = target.parent / "backups"
    stem, dot, suffix = target.name.partition(".")
    for n in range(1000):
        tag = stamp if n == 0 else f"{stamp}-{n}"
        candidate = base / f"{stem}.{tag}{dot}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"no free backup name for {target.name} in {base}")


def _not_built_yet(command: str) -> int:
    print(
        f"'{command}' is not implemented yet: the application code does not exist.\n"
        "It is scheduled for a later build step. Nothing was run.",
        file=sys.stderr,
    )
    return 2


COMMANDS = {
    "setup": setup,
    "check": check,
    "serve": serve,
    "eval-fast": eval_fast,
    "run": run,
    "demo-three-days": demo_three_days,
    "probe-protocol-version": probe_protocol_version,
    "reset-demo": reset_demo,
}


def _demo_days_flag(args: list[str]) -> bool:
    """``--demo-days-later N`` (serve and run only): hand N to the server as CLUCKTALK_DEMO_DAYS_LATER. The server
    validates the value and refuses it outside demo mode. Returns False when the arguments are not understood."""
    if args == []:
        return True
    if len(args) == 2 and args[0] == "--demo-days-later" and args[1].isdigit():
        os.environ["CLUCKTALK_DEMO_DAYS_LATER"] = args[1]
        return True
    return False


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    extra = sys.argv[2:]
    if sys.argv[1] == "reset-demo":
        return reset_demo(extra)
    if extra and not (sys.argv[1] in ("serve", "run") and _demo_days_flag(extra)):
        print(__doc__)
        return 2
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
