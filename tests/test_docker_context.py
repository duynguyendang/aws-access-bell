import fnmatch
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _patterns():
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _ignored(path, patterns):
    parts = path.split("/")
    for pattern in patterns:
        clean = pattern.rstrip("/")
        depth = len(clean.split("/"))
        prefix = "/".join(parts[:depth])
        if fnmatch.fnmatch(prefix, clean) or fnmatch.fnmatch(path, clean):
            return True
    return False


def _copy_sources():
    sources = []
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*COPY\s+(.+)$", line, re.IGNORECASE)
        if not match:
            continue
        args = [token for token in match.group(1).split() if not token.startswith("--")]
        if len(args) >= 2:
            args = args[:-1]
        sources.extend(args)
    return sources


def test_dockerfile_copy_sources_survive_dockerignore():
    patterns = _patterns()
    problems = []
    for source in _copy_sources():
        relative = source.strip("/") or "."
        if not (ROOT / relative).exists():
            problems.append(f"COPY source {source!r} does not exist in the repo")
        elif _ignored(relative, patterns):
            problems.append(f"COPY source {source!r} is excluded by .dockerignore")
    assert problems == []


@pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0, reason="git missing")
def test_shell_scripts_are_committed_executable():
    listed = subprocess.run(["git", "ls-files", "-s", "scripts"], capture_output=True, text=True, cwd=ROOT, check=True)
    modes = {}
    for line in listed.stdout.splitlines():
        meta, path = line.split("\t", 1)
        modes[path.strip()] = meta.split()[0]
    shell_files = {path: mode for path, mode in modes.items() if path.endswith(".sh")}
    assert shell_files, "expected shell scripts under scripts/"
    assert {p: m for p, m in shell_files.items() if m != "100755"} == {}


def test_requirements_files_are_copied_before_install():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY requirements.txt requirements-llm.txt ./" in dockerfile
    for name in ("requirements.txt", "requirements-dev.txt", "requirements-postgres.txt"):
        assert (ROOT / name).exists(), name
