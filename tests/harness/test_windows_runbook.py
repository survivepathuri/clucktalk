"""Step 53 part D: what the Windows runbook tells the builder, and the honest README paragraph. Text checks only."""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = (ROOT / "docs" / "PILOT_RUNBOOK_WINDOWS.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_runbook_names_the_one_forwarded_port_and_the_tailscale_commands_for_the_builder():
    assert "tailscale funnel --bg 8766" in RUNBOOK
    assert "tailscale funnel status" in RUNBOOK
    assert "tailscale funnel --https=443 off" in RUNBOOK
    assert "8765" in RUNBOOK and "never forwarded" in RUNBOOK
    assert "tailscale funnel --bg 8765" not in RUNBOOK
    assert "you run these yourself" in RUNBOOK


def test_the_runbook_names_the_farm_file_fields_and_keeps_the_real_file_outside_the_repository():
    for needle in ("birds_placed", "placed_on", "deaths_before_pilot", "pilot_farm.example.json", "never committed"):
        assert needle in RUNBOOK, needle
    assert r"C:\clucktalk-pilot\pilot_farm.json" in RUNBOOK
    for path in re.findall(r"C:\\clucktalk-pilot[^\s`'\"<>)]*", RUNBOOK):
        assert PureWindowsPath(path).parts[1].lower() == "clucktalk-pilot"
        assert str(ROOT).lower() not in path.lower()


def test_the_first_run_checklist_covers_the_link_the_notice_a_cancelled_record_and_the_401():
    first = RUNBOOK.split("## 7. First-run check")[1].split("## 8.")[0].lower()
    for needle in ("farmer link", "notice", "cancel", "401", "/api/state", "mobile data", "kill-switch.ps1"):
        assert needle in first, needle


def test_the_runbook_has_the_power_cut_backup_usb_and_delete_steps_with_the_exact_schtasks_command():
    assert "start-pilot.cmd" in RUNBOOK.split("## 8.")[1].split("## 9.")[0]
    assert re.search(r"schtasks /Create /TN \"[^\"]+\" /SC DAILY /ST 02:30", RUNBOOK)
    assert "Review this command" in RUNBOOK
    assert "backup-pilot.ps1 -CopyTo" in RUNBOOK
    delete = RUNBOOK.split("## 12. Delete on request")[1].split("## 13.")[0]
    for needle in ("-journal", "-wal", "-shm", "backups", "USB", "logs", "token"):
        assert needle in delete, needle
    who = RUNBOOK.split("## 13. Who can read")[1].lower()
    assert "anyone with access to this pc" in who and "the builder" in who


def test_the_runbook_makes_no_claim_about_uptime_and_names_no_real_funnel_host():
    assert (".ts" + ".net") not in RUNBOOK + README  # the real Funnel host lives only in the private env file
    assert "<your-funnel-host>" in RUNBOOK
    assert "Nothing here promises or measures uptime" in RUNBOOK
    assert not re.search(r"\b\d+(\.\d+)?\s*%\s*(uptime|available)", RUNBOOK + README, re.I)


def test_the_readme_limitations_carry_the_honest_paragraph_and_the_claims_table_does_not_overclaim():
    limits = README.split("## Known limitations")[1].split("## What is verified")[0]
    assert (
        "builder's own PC, published through a free Tailscale Funnel; availability depends on that PC and its internet"
        in limits
    )
    claims = README.split("## What is verified, unverified and simulated")[1].split("\n## ")[0]
    rows = [
        r for r in claims.splitlines() if "Windows launcher" in r or "builder's own PC through a Tailscale Funnel" in r
    ]
    assert len(rows) == 2
    launcher, running = rows
    assert "| VERIFIED (text checks" in launcher and "test_windows_launcher.py" in launcher
    # Updated 2026-10-13 (owner-authorised): no farmer has used the pilot yet; the row stays UNVERIFIED, no usage claim.
    shared = "| UNVERIFIED (no farmer has used the pilot yet, so usage numbers are pending"
    assert shared in running
    assert "VERIFIED" not in running.replace("UNVERIFIED", "")
