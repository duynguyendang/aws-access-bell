"""Fail when prose and data drift apart (test count, MCP tool catalog, caption rules).

With --strict-submission (or SUBMISSION_STRICT=1) it also fails while the README
still carries TODO(submission) placeholders for the demo URL / video link.

Usage: python scripts/check_docs_consistency.py [--strict-submission]
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def check_tool_catalog() -> list[str]:
    from backend.mcp_server import TOOLS

    count = len(TOOLS)
    problems = []
    readme = _read("README.md")
    architecture = _read("docs/ARCHITECTURE.md")
    if f"{count} tools" not in readme:
        problems.append(f"README.md should mention '{count} tools'")
    for stale in (
        f"{count - 1} tools",
        f"{count + 1} tools",
        f"{count - 1} door tools",
        f"{count + 1} door tools",
    ):
        if stale in readme:
            problems.append(f"README.md has stale '{stale}'")
        if stale in architecture:
            problems.append(f"docs/ARCHITECTURE.md has stale '{stale}'")
    # Catch any other stale count, e.g. "All **8** AccessBell MCP tools".
    for label, text in (("README.md", readme), ("docs/ARCHITECTURE.md", architecture)):
        for match in re.finditer(r"(\d+)\s+door tools", text):
            if int(match.group(1)) != count:
                problems.append(f"{label} has stale '{match.group(0)}'")
        for match in re.finditer(r"\*\*(\d+)\*\*[^\n|]*MCP tools", text):
            if int(match.group(1)) != count:
                problems.append(f"{label} has stale '{match.group(0)}'")
    return problems


def check_caption_rules() -> list[str]:
    problems = []
    source = _read("backend/captions.py")
    # The forbidden phrases are written as escapes so this checker stays ASCII-only
    # (Vietnamese literals are only allowed in backend/captions.py).
    forbidden = (" \u1edf ca", "s\u1ee1 ki\u1ec7n ca")
    if any(phrase in source for phrase in forbidden):
        problems.append("backend/captions.py contains the Vietnamese 'ca' typo")
    from backend import captions

    for language in captions.LANGUAGES:
        for key, template in captions.BRIEF[language].items():
            if key == "urgent":
                continue
            rendered = captions.render(template, 2)
            if not captions.is_tts_safe(rendered) or not captions.is_short_enough(rendered):
                problems.append(f"BRIEF template {language}/{key} violates caption rules")
    return problems


def check_slo_docs() -> list[str]:
    from backend.config import Settings

    readme = _read("README.md")
    problems = []
    for name in ("CONTEXT_BUDGET_MS", "ENRICH_BUDGET_MS"):
        if name not in readme:
            problems.append(f"README.md should document {name}")
    if "p95" not in readme:
        problems.append("README.md should state the p95 SLO")
    settings = Settings()
    if settings.context_budget_ms <= 0 or settings.enrich_budget_ms <= 0:
        problems.append("latency budgets must be positive")
    return problems


def collect_test_count() -> int | None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    match = re.search(r"(\d+) tests collected", result.stdout)
    return int(match.group(1)) if match else None


def check_test_count(collected: int | None = None) -> list[str]:
    readme = _read("README.md")
    match = re.search(r"\*\*(\d+) tests\*\*", readme)
    if not match:
        return ["README.md is missing a '**N tests**' marker"]
    claimed = int(match.group(1))
    actual = collected if collected is not None else collect_test_count()
    if actual is not None and actual != claimed:
        return [f"README.md claims {claimed} tests but pytest collects {actual}"]
    return []


def check_submission_ready(readme: str | None = None) -> list[str]:
    text = _read("README.md") if readme is None else readme
    problems = []
    if "TODO(submission)" in text:
        problems.append("README.md still has TODO(submission) placeholders (demo URL / video link)")
    return problems


def main() -> int:
    strict = "--strict-submission" in sys.argv or os.environ.get("SUBMISSION_STRICT") == "1"
    problems = (
        check_tool_catalog() + check_caption_rules() + check_test_count() + check_slo_docs()
    )
    if strict:
        problems += check_submission_ready()
    if problems:
        for problem in problems:
            print(f"DRIFT: {problem}")
        return 1
    print("docs consistency OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())