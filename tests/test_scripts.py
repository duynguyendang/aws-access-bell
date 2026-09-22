import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ablation_script_shows_grounding_contribution():
    ablation = _load("ablation_evidence", "scripts/ablation_evidence.py")
    report = ablation.run()
    assert set(report["arms"]) == {"event_only", "payload_hints", "expected_window"}
    assert report["arms"]["event_only"] < report["arms"]["expected_window"]
    assert report["arms"]["payload_hints"] == 1.0
    assert "event_only" in ablation.render(report)


def test_demo_story_script_is_wired():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "demo_story.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    for flag in ("--calendar", "--escalate", "--demote", "--token", "--pace"):
        assert flag in result.stdout


def test_consistency_script_reports_clean():
    checker = _load("check_docs_consistency", "scripts/check_docs_consistency.py")
    assert checker.check_tool_catalog() == []
    assert checker.check_caption_rules() == []
    assert checker.check_slo_docs() == []
    claimed = int(re.search(r"\*\*(\d+) tests\*\*", (ROOT / "README.md").read_text(encoding="utf-8")).group(1))
    assert checker.check_test_count(collected=claimed) == []
    assert checker.check_test_count(collected=claimed + 1) != []