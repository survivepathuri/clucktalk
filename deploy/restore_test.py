"""Restore test (Step 51 part E): prove a backup can be used, without touching the live file.

    python deploy/restore_test.py --dest /var/backups/clucktalk-pilot [--backup FILE] [--live STATE]

It takes the newest backup in ``--dest`` (or ``--backup``), copies it to a temporary folder, and checks that the copy
passes ``PRAGMA integrity_check``, that the application's own store opens it (the schema is the one this code expects),
and, with ``--live``, that it has the same tables as the live file. It prints table names and row COUNTS only, never a
row. Nothing outside the temporary folder is written. Exit code 0 only when every check passed: run it after every
backup change, and at least once before the pilot starts.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def tables(path: Path) -> dict[str, int]:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        listing = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        names = [r[0] for r in db.execute(listing)]
        return {n: db.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in sorted(names)}
    finally:
        db.close()


def newest(dest: Path) -> Path:
    found = sorted(p for p in dest.glob("*.sqlite3") if p.is_file())
    if not found:
        raise SystemExit(f"restore test: no backup in {dest}")
    return found[-1]


def restore_test(backup: Path, live: Path | None = None) -> dict[str, int]:
    if not backup.is_file():
        raise SystemExit(f"restore test: no such backup {backup}")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        restored = Path(tmp) / backup.name
        shutil.copyfile(backup, restored)
        db = sqlite3.connect(restored)
        try:
            verdict = db.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as exc:  # not even a database any more
            raise SystemExit(f"restore test: the backup cannot be read as a database: {exc}") from exc
        finally:
            db.close()
        if verdict != ("ok",):
            raise SystemExit(f"restore test: integrity check failed: {verdict}")
        counts = tables(restored)
        if live is not None:
            missing = sorted(set(tables(live)) - set(counts))
            if missing:
                raise SystemExit(f"restore test: the backup lacks table(s) {missing} that the live file has")
        sys.path.insert(0, str(ROOT / "src"))
        from clucktalk.store.sqlite import SqliteStore  # the application's own store, on the temporary copy

        try:
            SqliteStore(restored).close()
        except Exception as exc:  # noqa: BLE001 - any failure to open is the test failing; it is reported, never hidden
            raise SystemExit(f"restore test: the application could not open the restored file: {exc}") from exc
        return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that the newest backup can be restored.")
    parser.add_argument("--dest", type=Path, help="the backup folder (the newest .sqlite3 file is used)")
    parser.add_argument("--backup", type=Path, help="a specific backup file")
    parser.add_argument("--live", type=Path, help="the live state file, to compare its tables")
    args = parser.parse_args(argv)
    if (args.dest is None) == (args.backup is None):
        parser.error("give exactly one of --dest and --backup")
    backup = args.backup or newest(args.dest)
    counts = restore_test(backup, args.live)
    print(f"restore test: PASS for {backup.name}")
    for name, rows in counts.items():
        print(f"  {name}: {rows} row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
