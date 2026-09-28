"""State store: what the farmer changes (profile, proposals awaiting "yes", daily records) (docs/DESIGN.md §13.1).

Tools depend on the ``Store`` interface only. Local mode uses ``SqliteStore`` (Python's built-in sqlite3, a file
under ``.local/``); a cloud store can replace it without touching the tools. Reads are single-row lookups, well
inside the 500 ms tool budget (Rule 4).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from clucktalk.domain.models import DailyRecord
from clucktalk.domain.profile import FarmProfile
from clucktalk.domain.proposals import Proposal


class StoreError(RuntimeError):
    """The store cannot be used (e.g. a file from an incompatible version). Fails loud at startup (Rule 6)."""


class Store(Protocol):
    def atomic(self) -> AbstractContextManager[None]:
        """Everything inside happens together or not at all, and no other writer interleaves."""
        ...

    def get_profile(self, farm_id: str) -> FarmProfile | None: ...

    def save_profile(self, profile: FarmProfile) -> None: ...

    def add_proposal(self, proposal: Proposal) -> None: ...

    def get_proposal(self, proposal_id: str) -> Proposal | None: ...

    def pending_proposals(self, farm_id: str, tool: str) -> list[Proposal]: ...

    def update_proposal(self, proposal: Proposal) -> None:
        """Save a proposal's new status, resolved_at and outcome (its change itself never changes)."""
        ...

    def put_record(self, farm_id: str, house_id: str, record: DailyRecord) -> None:
        """Save one house's record for one day, replacing an earlier record for that day."""
        ...

    def records(self, farm_id: str, house_id: str) -> tuple[DailyRecord, ...]:
        """Saved records for one house, sorted by day."""
        ...
