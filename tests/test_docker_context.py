import fnmatch
import re
from pathlib import Path

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


def test_requirements_files_are_copied_before_install():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY requirements.txt requirements-llm.txt ./" in dockerfile
    for name in ("requirements.txt", "requirements-dev.txt", "requirements-postgres.txt"):
        assert (ROOT / name).exists(), name
