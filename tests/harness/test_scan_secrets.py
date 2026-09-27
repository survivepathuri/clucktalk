"""The secret scan must catch committed credentials and stray .env files before they reach git."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import scan_secrets  # noqa: E402

# Built at runtime so the repo itself never contains a credential-shaped string.
FAKE_AWS_KEY_ID = "AKIA" + "Z" * 16


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_clean_repo_passes(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "README.md").write_text("CluckTalk\n", encoding="utf-8")
    (repo / ".env.example").write_text("AWS_REGION=\n", encoding="utf-8")
    assert scan_secrets.main(["--root", str(repo)]) == 0


def test_aws_key_in_source_fails(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "config.py").write_text(f'KEY = "{FAKE_AWS_KEY_ID}"\n', encoding="utf-8")
    assert scan_secrets.main(["--root", str(repo)]) == 1


def test_unignored_env_file_fails(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / ".env").write_text("MOCK_BEDROCK=true\n", encoding="utf-8")
    assert scan_secrets.main(["--root", str(repo)]) == 1


def test_gitignored_env_file_is_allowed(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repo / ".env").write_text(f"AWS_ACCESS_KEY_ID={FAKE_AWS_KEY_ID}\n", encoding="utf-8")
    assert scan_secrets.main(["--root", str(repo)]) == 0


def test_not_a_git_repo_is_an_error_not_a_pass(tmp_path):
    assert scan_secrets.main(["--root", str(tmp_path)]) == 2


def test_unignored_private_notes_fail(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "private").mkdir()
    (repo / "private" / "notes.md").write_text("plan\n", encoding="utf-8")
    assert scan_secrets.main(["--root", str(repo)]) == 1


def test_unignored_claude_local_fails(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "CLAUDE.local.md").write_text("@private/x.md\n", encoding="utf-8")
    assert scan_secrets.main(["--root", str(repo)]) == 1


def test_gitignored_private_notes_are_allowed(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / ".gitignore").write_text("private/\nCLAUDE.local.md\n", encoding="utf-8")
    (repo / "private").mkdir()
    (repo / "private" / "notes.md").write_text("plan\n", encoding="utf-8")
    (repo / "CLAUDE.local.md").write_text("@private/notes.md\n", encoding="utf-8")
    assert scan_secrets.main(["--root", str(repo)]) == 0
