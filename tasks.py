"""CluckTalk task runner: one cross-platform entry point, standard library only (CLAUDE.md Rule 12).

Windows (cmd):
    python tasks.py setup       Create .venv with Python 3.13 (via the py launcher) and install pinned deps
    python tasks.py check       Lint + unit + contract tests + AOSS check + secret scan (Rule 3)
    python tasks.py eval-fast   Golden eval suite in mock mode, no AWS needed
    python tasks.py serve       Start only the MCP server (demo data, http://127.0.0.1:8765/mcp)
    python tasks.py run         Start the local demo (Simulator + MCP server, mock mode)

Every step prints PASS / FAIL / SKIP, and the run exits non-zero if any step fails.
A skipped step is always shown with its reason. Nothing is silently skipped (Rule 6).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REQUIRED_PYTHON = (3, 13)
REQUIRED_PYTHON_STR = "3.13"
ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
DEV_REQUIREMENTS = ROOT / "requirements-dev.txt"
APP_REQUIREMENTS = ROOT / "requirements.txt"
PYTEST_NO_TESTS_COLLECTED = 5


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
    """Command that starts the required Python, even when tasks.py runs under another version."""
    if sys.version_info[:2] == REQUIRED_PYTHON:
        return [sys.executable]
    launcher = shutil.which("py")
    if launcher and subprocess.call([launcher, f"-{REQUIRED_PYTHON_STR}", "-c", ""], stderr=subprocess.DEVNULL) == 0:
        return [launcher, f"-{REQUIRED_PYTHON_STR}"]
    unix_name = shutil.which(f"python{REQUIRED_PYTHON_STR}")
    if unix_name:
        return [unix_name]
    sys.exit(
        f"ERROR: Python {REQUIRED_PYTHON_STR} not found. Install it, e.g. on Windows: py install {REQUIRED_PYTHON_STR}"
    )


def _require_venv() -> None:
    version = _venv_python_version()
    if version is None:
        sys.exit("ERROR: .venv not found. Run 'python tasks.py setup' first.")
    if version != REQUIRED_PYTHON:
        sys.exit(
            f"ERROR: .venv uses Python {version[0]}.{version[1]}, project requires {REQUIRED_PYTHON_STR}. "
            "Run 'python tasks.py setup' to recreate it."
        )


def setup() -> int:
    version = _venv_python_version()
    if version is not None and version != REQUIRED_PYTHON:
        print(f"Existing .venv uses Python {version[0]}.{version[1]}; recreating it with {REQUIRED_PYTHON_STR} ...")
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
                else ("FAIL", "run: .venv\\Scripts\\python -m ruff format .")
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


def serve() -> int:
    """MCP server only. Demo mode is switched on here, explicitly and visibly (Rule 6)."""
    _require_venv()
    env = dict(os.environ)
    if env.get("MOCK_BEDROCK", "").strip() == "":
        env["MOCK_BEDROCK"] = "true"
        print("serve: MOCK_BEDROCK not set, so starting in DEMO DATA mode (MOCK_BEDROCK=true).", flush=True)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    try:
        return subprocess.call([str(VENV_PY), "-m", "clucktalk.server"], cwd=ROOT, env=env)
    except KeyboardInterrupt:
        print("serve: stopped.")
        return 0


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
    "eval-fast": lambda: _not_built_yet("eval-fast"),
    "run": lambda: _not_built_yet("run"),
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
