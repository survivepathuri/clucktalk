"""``SqliteStore``: the local state store, on Python's built-in sqlite3 (no extra dependency).

One connection per store, guarded by a lock, so tool calls from any thread see one consistent state. Writes run
in ``BEGIN IMMEDIATE`` transactions; ``atomic()`` groups several reads and writes (e.g. check a proposal is still
pending, apply its change, mark it confirmed) so a repeated "yes" can never apply twice.
Timestamps are stored as ISO 8601 with their UTC offset; JSON columns hold canonical JSON.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from clucktalk.domain.models import DailyRecord, Treatment, TreatmentKind
from clucktalk.domain.profile import FarmMode, FarmProfile
from clucktalk.domain.proposals import Proposal, ProposalStatus, canonical
from clucktalk.store import StoreError

MEMORY = ":memory:"
SCHEMA_VERSION = "1"
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (
    farm_id TEXT PRIMARY KEY, mode TEXT NOT NULL, set_by TEXT NOT NULL, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY, farm_id TEXT NOT NULL, tool TEXT NOT NULL, arguments TEXT NOT NULL,
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL, resolved_at TEXT, outcome TEXT
);
CREATE INDEX IF NOT EXISTS proposals_by_tool ON proposals (farm_id, tool, status);
CREATE TABLE IF NOT EXISTS records (
    farm_id TEXT NOT NULL, house_id TEXT NOT NULL, day TEXT NOT NULL, record TEXT NOT NULL,
    PRIMARY KEY (farm_id, house_id, day)
);
"""


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _iso(value: datetime | None) -> str | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("store timestamps must carry a timezone")
    return None if value is None else value.isoformat()


def record_to_json(record: DailyRecord) -> str:
    return canonical(
        {
            "day": record.day.isoformat(),
            "deaths": record.deaths,
            "feed_kg": record.feed_kg,
            "avg_weight_g": record.avg_weight_g,
            "eggs": record.eggs,
            "weight_sample_birds": record.weight_sample_birds,
            "treatments": [{"kind": t.kind.value, "name": t.name, "note": t.note} for t in record.treatments],
        }
    )


def record_from_json(text: str) -> DailyRecord:
    d = json.loads(text)
    return DailyRecord(
        day=date.fromisoformat(d["day"]),
        deaths=d["deaths"],
        feed_kg=d["feed_kg"],
        avg_weight_g=d["avg_weight_g"],
        eggs=d["eggs"],
        weight_sample_birds=d["weight_sample_birds"],
        treatments=tuple(Treatment(TreatmentKind(t["kind"]), t["name"], t["note"]) for t in d["treatments"]),
    )


class SqliteStore:
    def __init__(self, path: Path | str = MEMORY) -> None:
        self.path = str(path)
        if self.path != MEMORY:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: no implicit transactions; atomic() issues BEGIN IMMEDIATE / COMMIT itself.
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        with self.atomic():
            # Statement by statement: executescript() would COMMIT the transaction atomic() just opened.
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    self._db.execute(statement)
            row = self._db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            if row is None:
                self._db.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
            elif row["value"] != SCHEMA_VERSION:
                raise StoreError(
                    f"{self.path} has state schema {row['value']}, this version needs {SCHEMA_VERSION}. "
                    "Run: python tasks.py reset-demo"
                )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._db.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if outer:
                    self._db.execute("ROLLBACK")
                raise
            self._depth -= 1
            if outer:
                try:
                    self._db.execute("COMMIT")
                except sqlite3.Error:
                    # Never leave the connection inside a half-done transaction (every later atomic() would fail
                    # and reads would see uncommitted writes): undo it, then fail loud.
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    raise

    # -- profile -------------------------------------------------------------------------------------------------
    def get_profile(self, farm_id: str) -> FarmProfile | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM profiles WHERE farm_id = ?", (farm_id,)).fetchone()
        if row is None:
            return None
        return FarmProfile(row["farm_id"], FarmMode(row["mode"]), row["set_by"], _dt(row["updated_at"]))

    def save_profile(self, profile: FarmProfile) -> None:
        with self.atomic():
            self._db.execute(
                "INSERT OR REPLACE INTO profiles (farm_id, mode, set_by, updated_at) VALUES (?, ?, ?, ?)",
                (profile.farm_id, profile.mode.value, profile.set_by, _iso(profile.updated_at)),
            )

    # -- proposals -----------------------------------------------------------------------------------------------
    @staticmethod
    def _proposal(row: sqlite3.Row) -> Proposal:
        outcome: dict[str, Any] | None = None if row["outcome"] is None else json.loads(row["outcome"])
        return Proposal(
            proposal_id=row["proposal_id"],
            farm_id=row["farm_id"],
            tool=row["tool"],
            arguments=json.loads(row["arguments"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            status=ProposalStatus(row["status"]),
            resolved_at=_dt(row["resolved_at"]),
            outcome=outcome,
        )

    def add_proposal(self, proposal: Proposal) -> None:
        with self.atomic():
            self._db.execute(
                "INSERT INTO proposals (proposal_id, farm_id, tool, arguments, created_at, expires_at, status, "
                "resolved_at, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal.proposal_id,
                    proposal.farm_id,
                    proposal.tool,
                    canonical(proposal.arguments),
                    _iso(proposal.created_at),
                    _iso(proposal.expires_at),
                    proposal.status.value,
                    _iso(proposal.resolved_at),
                    None if proposal.outcome is None else canonical(proposal.outcome),
                ),
            )

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        return None if row is None else self._proposal(row)

    def pending_proposals(self, farm_id: str, tool: str) -> list[Proposal]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM proposals WHERE farm_id = ? AND tool = ? AND status = ? ORDER BY created_at",
                (farm_id, tool, ProposalStatus.PENDING.value),
            ).fetchall()
        return [self._proposal(r) for r in rows]

    def update_proposal(self, proposal: Proposal) -> None:
        with self.atomic():
            cur = self._db.execute(
                "UPDATE proposals SET status = ?, resolved_at = ?, outcome = ? WHERE proposal_id = ?",
                (
                    proposal.status.value,
                    _iso(proposal.resolved_at),
                    None if proposal.outcome is None else canonical(proposal.outcome),
                    proposal.proposal_id,
                ),
            )
            if cur.rowcount != 1:
                raise StoreError(f"proposal {proposal.proposal_id} does not exist")

    # -- records -------------------------------------------------------------------------------------------------
    def put_record(self, farm_id: str, house_id: str, record: DailyRecord) -> None:
        with self.atomic():
            self._db.execute(
                "INSERT OR REPLACE INTO records (farm_id, house_id, day, record) VALUES (?, ?, ?, ?)",
                (farm_id, house_id, record.day.isoformat(), record_to_json(record)),
            )

    def records(self, farm_id: str, house_id: str) -> tuple[DailyRecord, ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT record FROM records WHERE farm_id = ? AND house_id = ? ORDER BY day", (farm_id, house_id)
            ).fetchall()
        return tuple(record_from_json(r["record"]) for r in rows)
