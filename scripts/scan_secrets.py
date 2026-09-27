"""Rule 9 guard: fail if a credential-looking string or a real .env file would be committed.

Scans every file git would track (tracked + untracked-but-not-ignored), so it runs before the
first commit too. Exit codes: 0 = clean, 1 = secret found, 2 = scan could not run.
Usage (Windows):  python scripts\\scan_secrets.py [--root PATH]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECRET_PATTERNS = {
    "AWS access key ID": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "AWS secret access key": re.compile(r"aws_?secret_?access_?key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}\b", re.IGNORECASE),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
    "Anthropic API key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    "OpenAI-style API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
}
# .env files hold real values; only the committed template is allowed.
ALLOWED_ENV_FILES = {".env.example"}
MAX_BYTES = 2_000_000


def _candidate_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    names = [n for n in result.stdout.decode("utf-8").split("\0") if n]
    return [root / n for n in names]


def scan(root: Path) -> tuple[list[str], int]:
    findings: list[str] = []
    files = _candidate_files(root)
    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.name.startswith(".env") and path.name not in ALLOWED_ENV_FILES:
            findings.append(f"{rel}: .env file is not git-ignored (never commit real env files)")
            continue
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary file (image, font); not a text secret carrier
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{rel}:{lineno}: looks like a {label}")
    return findings, len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    root = args.root.resolve()

    try:
        findings, count = scan(root)
    except FileNotFoundError:
        print("Secret scan could not run: 'git' is not on PATH.", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "replace").strip()
        print(f"Secret scan could not run: git failed ({stderr}). Is this a git repo?", file=sys.stderr)
        return 2

    print(f"Secret scan: scanned {count} file(s) that git would commit.")
    for f in findings:
        print(f"  FOUND  {f}", file=sys.stderr)
    if findings:
        print("Secret scan FAILED: remove the secret, rotate it if it was ever shared.", file=sys.stderr)
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
