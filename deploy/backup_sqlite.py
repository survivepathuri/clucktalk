"""Daily backup of an instance's SQLite state (Step 51 part E). Standard library only; run it from cron or the timer.

    python deploy/backup_sqlite.py --state /var/lib/clucktalk-pilot/state/pilot_state.sqlite3 \
        --dest /var/backups/clucktalk-pilot [--also usage.json ...] [--keep 14]

It uses SQLite's own online backup (safe while the server is running, never a plain file copy of a live
database), checks the copy with ``PRAGMA integrity_check`` before keeping it, writes it readable only by its
owner, and keeps the newest ``--keep`` backups. It never touches the live file except to read it. The copy to
off-machine storage (a private bucket) is a separate step in docs/PILOT_RUNBOOK.md. Exit code 0 only when a good
backup exists now.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

STAMP = "%Y%m%d-%H%M%S"


def backup(state: Path, dest: Path, keep: int, also: list[Path], now: datetime | None = None) -> Path:
    if not state.is_file():
        raise SystemExit(f"backup: no state file at {state}")
    if keep < 1:
        raise SystemExit("backup: --keep must be at least 1")
    dest.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime(STAMP)
    target = dest / f"{state.stem}_{stamp}{state.suffix}"
    if target.exists():
        raise SystemExit(f"backup: {target.name} already exists (two backups in the same second)")
    source = sqlite3.connect(f"file:{state}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)  # the online backup API
    finally:
        copy.close()
        source.close()
    check = sqlite3.connect(target)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()
    finally:
        check.close()
    if result != ("ok",):
        target.unlink()
        raise SystemExit(f"backup: the copy failed its integrity check ({result}); it was removed")
    os.chmod(target, 0o600)
    for extra in also:
        if extra.is_file():
            copied = dest / f"{extra.stem}_{stamp}{extra.suffix}"
            shutil.copyfile(extra, copied)
            os.chmod(copied, 0o600)
    prune(dest, state.stem, state.suffix, keep)
    return target


def prune(dest: Path, stem: str, suffix: str, keep: int) -> None:
    old = sorted(p for p in dest.glob(f"{stem}_*{suffix}") if p.is_file())
    for path in old[:-keep]:
        path.unlink()
        for extra in dest.glob(f"*_{path.name.removeprefix(stem + '_').removesuffix(suffix)}.*"):
            extra.unlink()  # the files saved with it


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up an instance's SQLite state.")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--also", type=Path, action="append", default=[], help="another file to keep with it")
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args(argv)
    print(f"backup: wrote {backup(args.state, args.dest, args.keep, args.also)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
