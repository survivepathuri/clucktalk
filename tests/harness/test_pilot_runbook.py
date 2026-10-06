"""Step 52 parts C and D: what the runbook tells the operator, checked for the steps that keep the farmer's data
safe."""

from __future__ import annotations

import re
from pathlib import Path

RUNBOOK = (Path(__file__).resolve().parents[2] / "docs" / "PILOT_RUNBOOK.md").read_text(encoding="utf-8")


def section(title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}.*?(?=^## |\Z)", RUNBOOK, re.S | re.M)
    assert match, f"no section {title!r}"
    return match.group(0)


def test_the_backup_folder_is_made_for_the_pilot_user_with_mode_700_before_the_first_backup():
    deploy = section("Deploy (first time)")
    assert re.search(r"install -d -o clucktalk-pilot -g clucktalk-pilot -m 700 /var/backups/clucktalk-pilot", deploy)
    assert deploy.index("/var/backups/clucktalk-pilot") < deploy.index("systemctl enable --now")  # before the timer


def test_restoring_moves_the_stale_journal_files_aside_too():
    restore = section("Backup and restore")
    for name in ("-journal", "-wal", "-shm"):
        assert name in restore
    assert "do not delete" in restore.lower()


def test_delete_on_request_lists_every_copy():
    delete = section("Delete on request").lower()
    for needle in ("state/backups", "journald", "bucket", "old versions", "usage_pilot.json", "-journal", "copies"):
        assert needle in delete, needle


def test_token_rotation_is_spelled_out_with_two_tokens_overlapping():
    rotation = section("Rotating a token").lower()
    for needle in ("two tokens", "overlap", "restart", "remove the old", "new link", "revok"):
        assert needle in rotation, needle
    assert rotation.index("add the new") < rotation.index("remove the old")


def test_the_deaths_before_pilot_step_and_the_notice_are_explained():
    deploy = section("Deploy (first time)")
    assert "deaths_before_pilot" in deploy and "Ask him" in deploy
    assert "seven items" in RUNBOOK and "acknowledge" in RUNBOOK.lower()


def test_the_hardening_that_was_skipped_is_named_with_its_reason():
    hardening = section("Service hardening").lower()
    assert "memorydenywriteexecute" in hardening and "systemcallfilter" in hardening
    assert "skipped" in hardening and "python" in hardening


def test_the_runbook_shows_how_to_read_the_backup_age():
    assert "pilot-stats --usage" in RUNBOOK and "--backups" in RUNBOOK and "26 hours" in RUNBOOK
