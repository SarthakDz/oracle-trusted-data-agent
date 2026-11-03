"""Repository hygiene checks that keep the WSL toolchain working."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".py", ".sql", ".sh", ".toml", ".md", ".yml", ".yaml", ".jsonl", ".txt"}


def _repo_files() -> list[Path]:
    # Tracked plus untracked-but-not-ignored, so new files are checked before their first commit.
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [ROOT / p for p in out]


def test_no_crlf():
    text_files = [p for p in _repo_files() if p.suffix in TEXT_SUFFIXES or p.name in ("Makefile", "Dockerfile", ".dockerignore", "Caddyfile")]
    assert text_files, "expected text files in the repo"
    offenders = [str(p.relative_to(ROOT)) for p in text_files if p.exists() and b"\r" in p.read_bytes()]
    assert offenders == []
