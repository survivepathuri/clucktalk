"""State store: what the farmer changes (profile, proposals awaiting "yes", daily records) (docs/DESIGN.md §13.1).

Tools depend on the ``Store`` interface only. Local mode uses ``SqliteStore`` (Python's built-in sqlite3, a file
under ``.local/``); a cloud store can replace it without touching the tools. Reads are single-row lookups, well
inside the 500 ms tool budget (Rule 4).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Any, Protocol

from clucktalk.domain.briefing import BriefingRank
from clucktalk.domain.follow_up import FollowUpAnswer
from clucktalk.domain.models import DailyRecord
from clucktalk.domain.profile import ContractTerms, FarmProfile
from clucktalk.domain.proposals import Proposal
from clucktalk.domain.triage import HealthCheck, VetHandoff


class StoreError(RuntimeError):
    """The store cannot be used (e.g. a file from an incompatible version). Fails loud at startup (Rule 6)."""


class Store(Protocol):
    def atomic(self) -> AbstractContextManager[None]:
        """Everything inside happens together or not at all, and no other writer interleaves."""
        ...

    def get_profile(self, farm_id: str) -> FarmProfile | None: ...

    def save_profile(self, profile: FarmProfile) -> None: ...

    def get_contract_terms(self, farm_id: str) -> ContractTerms | None: ...

    def save_contract_terms(self, terms: ContractTerms) -> None: ...

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

    def add_health_check(self, check: HealthCheck) -> None: ...

    def update_health_check(self, check: HealthCheck) -> None:
        """Save a check's new status and result (its input and floor never change)."""
        ...

    def get_health_check(self, check_id: str) -> HealthCheck | None: ...

    def latest_health_check(self, farm_id: str, house_id: str) -> HealthCheck | None: ...

    def recent_health_checks(self, farm_id: str, house_id: str, since_day: date) -> tuple[HealthCheck, ...]: ...

    def add_handoff(self, handoff: VetHandoff) -> None: ...

    def handoff_for_check(self, check_id: str) -> VetHandoff | None: ...

    def add_follow_up_answer(self, answer: FollowUpAnswer) -> None:
        """Append one confirmed follow-up answer. Append-only: there is no way to edit or remove one."""
        ...

    def follow_up_answers(self, farm_id: str, check_id: str) -> tuple[FollowUpAnswer, ...]:
        """Every answer saved for one check, in the order given."""
        ...

    def save_briefing_rank(self, rank: BriefingRank) -> None:
        """Keep the AI ordering for one farm-day (replacing an earlier one)."""
        ...

    def get_briefing_rank(self, farm_id: str, day: date) -> BriefingRank | None: ...

    def add_ai_call(
        self,
        at: datetime,
        agent: str,
        engine: str,
        model_id: str | None,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        outcome: str,
    ) -> None:
        """One live model call's real usage: the ledger behind the daily cap and every published cost figure."""
        ...

    def ai_calls(self, day: date) -> list[dict[str, Any]]: ...

    def count_ai_calls(self, day: date, agent: str | None = None) -> int: ...
