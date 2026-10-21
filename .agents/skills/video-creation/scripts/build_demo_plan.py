#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


def parse_srt_time(time_str: str) -> float:
    hours, minutes, seconds = time_str.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def format_seconds(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def parse_srt(srt_path: Path):
    content = srt_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", content.strip())
    cues = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        cue_id = lines[0]
        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            lines[1],
        )
        if not time_match:
            continue
        start_sec = parse_srt_time(time_match.group(1))
        end_sec = parse_srt_time(time_match.group(2))
        text = " ".join(lines[2:])
        cues.append(
            {
                "id": cue_id,
                "start": start_sec,
                "end": end_sec,
                "duration": end_sec - start_sec,
                "text": text,
            }
        )
    return cues


def main():
    parser = argparse.ArgumentParser(description="Build video timeline plan from SRT file")
    parser.add_argument(
        "--srt",
        type=Path,
        default=Path("docs/accessbell-demo.srt"),
        help="Path to input SRT file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/internal/DEMO_RECORDING_RUNBOOK.md"),
        help="Path to output runbook markdown",
    )
    args = parser.parse_args()

    cues = parse_srt(args.srt)
    total_duration = cues[-1]["end"] if cues else 0.0

    lines = [
        "# AccessBell Video Recording Runbook",
        "",
        f"**Source SRT**: `{args.srt}`  ",
        f"**Total Video Duration**: {format_seconds(total_duration)} ({total_duration:.1f}s)  ",
        f"**Target Limit**: 03:00 (180.0s) — Status: {'PASS' if total_duration <= 180 else 'FAIL: EXCEEDS LIMIT'}",
        "",
        "| Cue | Start | End | Duration | Narration | Visual Scene & Action |",
        "|---|---|---|---|---|---|",
    ]

    for cue in cues:
        cue_id = cue["id"]
        start_str = format_seconds(cue["start"])
        end_str = format_seconds(cue["end"])
        dur_str = f"{cue['duration']:.1f}s"
        narration = cue["text"].replace("|", "\\|")
        scene_hint = "Live UI / Architecture"
        if cue["start"] < 25:
            scene_hint = "Slide: `docs/slides/executive-summary.html`"
        elif cue["start"] < 50:
            scene_hint = "Slide: `docs/slides/architecture.html` (Alexa+ MCP focus)"
        elif cue["start"] < 75:
            scene_hint = "Browser UI: Webhook simulation & TV caption"
        elif cue["start"] < 105:
            scene_hint = "Terminal: Alexa+ MCP inspector invoking tools"
        elif cue["start"] < 135:
            scene_hint = "Browser UI: Consent-gated escalation flow"
        else:
            scene_hint = "Slide: Architecture wrap-up & GitHub repo"

        lines.append(
            f"| #{cue_id} | {start_str} | {end_str} | {dur_str} | {narration} | {scene_hint} |"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated recording runbook at: {args.output}")


if __name__ == "__main__":
    main()
