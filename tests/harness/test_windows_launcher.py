"""Step 53 part C: the Windows pilot launcher files (deploy/windows). Text checks only: nothing here starts a server,
runs PowerShell, or touches a network. The environment example must list exactly the variables the code reads in
pilot mode, hold placeholders only, and be accepted by the code's own settings loaders once the placeholders are filled;
no script may hold a token-like string or a hard-coded hostname; start-pilot.ps1 must contain its refusals; and the
documented data paths must lie outside the repository."""

from __future__ import annotations

import re
import secrets
from pathlib import Path, PureWindowsPath

import pytest

from clucktalk.config import ConfigError, load_settings
from clucktalk.simulator.__main__ import load_simulator_settings

ROOT = Path(__file__).resolve().parents[2]
WIN = ROOT / "deploy" / "windows"
FUNNEL_HOST = "dataanalyst.tail011920.ts.net"

# The variables the code reads in pilot mode (Step 53 part A), and where they belong in the example.
REQUIRED = {
    "CLUCKTALK_MODE",
    "MOCK_BEDROCK",
    "CLUCKTALK_AUTH_TOKEN",
    "CLUCKTALK_SIMULATOR_TOKENS",
    "CLUCKTALK_STATE_PATH",
    "CLUCKTALK_PILOT_FARM_PATH",
    "CLUCKTALK_PUBLIC_ORIGIN",  # optional in the code, but without it the tunnel's Host is refused (421)
}
OPTIONAL_ACTIVE = {
    "CLUCKTALK_INSTANCE_NAME",
    "CLUCKTALK_PORT",
    "CLUCKTALK_SIMULATOR_PORT",
    "CLUCKTALK_DAILY_DEATHS_RULE_PATH",
    "CLUCKTALK_USAGE_PATH",
    "CLUCKTALK_DISABLED_FILE",
    "CLUCKTALK_RATE_PER_MINUTE",
    "CLUCKTALK_MAX_SESSIONS",
}
OPTIONAL_COMMENTED = {"CLUCKTALK_WEATHER_RULES_PATH", "CLUCKTALK_WEATHER_LIVE"}
# Read by the code but deliberately NOT in the pilot's environment file, each for a stated reason.
NOT_LISTED = {
    "CLUCKTALK_HOST": "the MCP server must stay on 127.0.0.1 (start-pilot.ps1 refuses it)",
    "CLUCKTALK_DEMO_DAYS_LATER": "refused in pilot mode",
    "CLUCKTALK_ALLOWED_ORIGINS": "browser CORS for the MCP server, which is not exposed",
    "CLUCKTALK_AI_MAX_CALLS_PER_DAY": "live AI is off in the pilot",
    "CLUCKTALK_MCP_URL": "the default (loopback and the MCP port) is right",
    "CLUCKTALK_DISABLED": "the kill switch is the file, set by CLUCKTALK_DISABLED_FILE",
}


def text(name: str) -> str:
    return (WIN / name).read_text(encoding="utf-8")


def scripts() -> list[Path]:
    return sorted([*WIN.glob("*.ps1"), *WIN.glob("*.cmd")])


def example_lines() -> list[str]:
    return text("env.windows.example").splitlines()


def active() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in example_lines():
        if line.strip() and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def commented() -> set[str]:
    return {m.group(1) for line in example_lines() if (m := re.match(r"# (CLUCKTALK_[A-Z_]+)=", line))}


# -- the environment example ---------------------------------------------------------------------------------------
def test_the_example_lists_exactly_the_variables_the_code_reads_in_pilot_mode():
    code = {
        name
        for path in (ROOT / "src").rglob("*.py")
        for name in re.findall(r"\b(?:CLUCKTALK_[A-Z_]+|MOCK_BEDROCK)\b", path.read_text(encoding="utf-8"))
    }
    listed = set(active()) | commented()
    assert set(active()) == REQUIRED | OPTIONAL_ACTIVE
    assert commented() == OPTIONAL_COMMENTED
    assert listed | set(NOT_LISTED) == code, (
        "the code reads a variable the example neither lists nor explains: "
        f"{sorted(code - listed - set(NOT_LISTED))}; or the example lists one the code never reads: "
        f"{sorted((listed | set(NOT_LISTED)) - code)}"
    )
    assert not listed & set(NOT_LISTED)


def test_the_example_holds_placeholders_only_for_the_tokens_and_the_address():
    values = active()
    for name in ("CLUCKTALK_SIMULATOR_TOKENS", "CLUCKTALK_AUTH_TOKEN", "CLUCKTALK_PUBLIC_ORIGIN"):
        assert re.fullmatch(r".*<[A-Z_]+>.*", values[name]), f"{name} must stay a <PLACEHOLDER> in the example"
    assert values["CLUCKTALK_MODE"] == "pilot" and values["MOCK_BEDROCK"] == "true"
    assert FUNNEL_HOST not in text("env.windows.example")


def test_the_example_filled_in_is_accepted_by_the_codes_own_loaders_and_allows_the_funnel_host():
    env = {k: v for k, v in active().items()}
    env["CLUCKTALK_AUTH_TOKEN"] = secrets.token_urlsafe(32)
    env["CLUCKTALK_SIMULATOR_TOKENS"] = secrets.token_urlsafe(32)
    env["CLUCKTALK_PUBLIC_ORIGIN"] = f"https://{FUNNEL_HOST}"
    assert load_settings(env).mode == "pilot"
    settings = load_simulator_settings(env)
    assert settings.port == 8766 and settings.mcp_url == "http://127.0.0.1:8765/mcp"
    assert FUNNEL_HOST in settings.hosts
    assert f"https://{FUNNEL_HOST}" in settings.allowed_origins
    # The placeholders themselves are not a valid token: an unfilled file cannot start by accident.
    with pytest.raises(ConfigError):
        load_settings({**env, "CLUCKTALK_AUTH_TOKEN": active()["CLUCKTALK_AUTH_TOKEN"]})


# -- no secrets, no hostnames in the scripts -----------------------------------------------------------------------
def looks_like_a_token(word: str) -> bool:
    return (
        len(word) >= 32
        and re.search(r"[0-9]", word) is not None
        and re.search(r"[a-z]", word) is not None
        and re.search(r"[A-Z]", word) is not None
    )


def test_no_script_or_example_holds_a_token_like_string():
    files = [*scripts(), WIN / "env.windows.example"]
    assert len(files) >= 9
    for path in files:
        for word in re.findall(r"[A-Za-z0-9_-]{32,}", path.read_text(encoding="utf-8")):
            assert not looks_like_a_token(word), f"{path.name} holds a token-like string"


def test_the_token_detector_finds_a_real_looking_token():
    assert looks_like_a_token(secrets.token_urlsafe(32) + "aA1")
    assert not looks_like_a_token("CLUCKTALK_DAILY_DEATHS_RULE_PATH")


def test_no_script_holds_a_hostname_or_a_web_address_other_than_loopback():
    for path in scripts():
        body = path.read_text(encoding="utf-8")
        assert ".ts.net" not in body, f"{path.name} names a tunnel host"
        for url in re.findall(r"https?://[^\s'\"<>\[$]+", body):
            assert url.startswith("http://127.0.0.1:"), f"{path.name} holds the address {url}"
        assert not re.search(r"\b[a-z0-9-]+\.(?:com|org|net|io|in|dev)\b", body), f"{path.name} names a hostname"


def test_the_funnel_host_appears_only_in_docs_and_nothing_under_the_windows_folder():
    for path in WIN.iterdir():
        assert FUNNEL_HOST not in path.read_text(encoding="utf-8"), path.name
        assert ".ts.net" not in path.read_text(encoding="utf-8"), path.name


# -- start-pilot.ps1 -----------------------------------------------------------------------------------------------
def test_start_pilot_contains_each_refusal():
    body = text("start-pilot.ps1")
    for needle in (
        "is missing or still a placeholder",  # a required variable
        "CLUCKTALK_MODE must be pilot",
        "MOCK_BEDROCK must be true",
        "Test-WeakToken",  # a weak token
        "a token is weak",
        "every token must be different",
        "is inside the repository",  # a data path inside the repository
        "Test-InsideFolder",
        "is the demo's state file",  # the demo path
        ".local\\clucktalk.sqlite3",
        "must be an absolute path",
        "the farm file does not exist",
        "looks like the example file",
        "CLUCKTALK_HOST",  # the server must stay on loopback
        "must stay on 127.0.0.1",
        "the pilot already runs",
    ):
        assert needle in body, f"start-pilot.ps1 lost its refusal: {needle}"
    assert "scripts\\run_instance.py" in body and "-WindowStyle Hidden" in body
    assert "-RedirectStandardOutput" in body and "-RedirectStandardError" in body


def test_start_pilot_never_prints_a_value_of_the_environment_file():
    body = text("start-pilot.ps1")
    for line in body.splitlines():
        if re.match(r"\s*Write-Host", line):
            assert "$values[" not in line and "$all" not in line and "$t " not in line, line


def test_every_script_is_strict_ascii_and_lf_only():
    for path in scripts():
        raw = path.read_bytes()
        assert b"\r" not in raw, f"{path.name} has a carriage return"
        assert all(b < 128 for b in raw), f"{path.name} has a non-ASCII character"
        if path.suffix == ".ps1":
            assert "Set-StrictMode -Version Latest" in raw.decode() or path.name != "common.ps1"
    cmd = text("start-pilot.cmd").strip().splitlines()
    assert len(cmd) == 1 and cmd[0].startswith("powershell ") and ":" not in cmd[0].split()[0]


def test_the_only_cmd_wrapper_just_calls_powershell():
    assert [p.name for p in WIN.glob("*.cmd")] == ["start-pilot.cmd"]
    assert [p.name for p in WIN.glob("*.bat")] == []


def test_new_token_uses_a_cryptographic_generator_and_never_saves_the_link():
    body = text("new-token.ps1")
    assert "RandomNumberGenerator" in body and "New-Object byte[] 32" in body
    assert "Restrict-ToCurrentUser" in body and "icacls" in text("common.ps1")
    assert "Random " not in body and "Get-Random" not in body
    # The link is only ever written to the screen.
    assert "Out-File" not in body and "Add-Content" not in body and "Tee-Object" not in body
    for line in body.splitlines():
        if "#t=" in line:
            assert line.lstrip().startswith("Write-Host"), line


def test_the_backup_uses_the_sqlite_backup_api_and_the_restore_moves_the_old_files_aside():
    backup, restore = text("backup-pilot.ps1"), text("restore-pilot.ps1")
    assert "backup_sqlite.py" in backup and "restore_test.py" in backup and "-CopyTo" in backup
    assert "Copy-Item" not in backup.split("$CopyTo -ne")[0], "the database itself must not be copied as a plain file"
    api = (ROOT / "deploy" / "backup_sqlite.py").read_text(encoding="utf-8")
    assert ".backup(" in api and "integrity_check" in api and "LAST_GOOD_BACKUP" in api
    for suffix in ("-journal", "-wal", "-shm"):
        assert f"'{suffix}'" in restore
    assert "Move-Item" in restore and "Remove-Item" not in restore


# -- the documented paths lie outside the repository -----------------------------------------------------------------
def test_the_documented_state_and_farm_paths_are_outside_the_repository_and_not_the_demos():
    values = active()
    repo = PureWindowsPath(str(ROOT))
    for name in (
        "CLUCKTALK_STATE_PATH",
        "CLUCKTALK_PILOT_FARM_PATH",
        "CLUCKTALK_DAILY_DEATHS_RULE_PATH",
        "CLUCKTALK_USAGE_PATH",
        "CLUCKTALK_DISABLED_FILE",
    ):
        path = PureWindowsPath(values[name])
        assert path.is_absolute() and str(path).lower().startswith("c:\\clucktalk-pilot\\"), name
        assert path != repo and repo not in path.parents, f"{name} is inside the repository"
        assert ".local" not in path.parts, name
    assert "pilot" in PureWindowsPath(values["CLUCKTALK_STATE_PATH"]).name
    assert PureWindowsPath(values["CLUCKTALK_STATE_PATH"]).suffix == ".sqlite3"
    assert PureWindowsPath(values["CLUCKTALK_PILOT_FARM_PATH"]).name != "pilot_farm.example.json"
    assert not str(ROOT).lower().startswith("c:\\clucktalk-pilot")
