#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from pathlib import Path


def parse_srt_time(time_str: str) -> float:
    hours, minutes, seconds = time_str.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


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
        cues.append({"id": cue_id, "start": start_sec, "end": end_sec, "text": text})
    return cues


def main():
    parser = argparse.ArgumentParser(description="Assemble timed audio track from cue files")
    parser.add_argument(
        "--srt",
        type=Path,
        default=Path("docs/accessbell-demo.srt"),
        help="Path to input SRT file",
    )
    parser.add_argument(
        "--cues-dir",
        type=Path,
        default=Path("docs/internal/assets/narration_cues"),
        help="Directory containing cue_*.mp3 files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/internal/assets/narration_master.mp3"),
        help="Output timed audio file",
    )
    parser.add_argument(
        "--ffmpeg",
        type=str,
        default=".venv/bin/ffmpeg",
        help="Path to ffmpeg binary",
    )
    args = parser.parse_args()

    cues = parse_srt(args.srt)
    total_duration = cues[-1]["end"] + 1.0

    inputs = []
    filter_parts = []
    for i, cue in enumerate(cues):
        cue_file = args.cues_dir / f"cue_{cue['id']}.mp3"
        if not cue_file.exists():
            print(f"Error: Missing cue file {cue_file}", file=sys.stderr)
            sys.exit(1)
        inputs.extend(["-i", str(cue_file)])
        delay_ms = int(cue["start"] * 1000)
        filter_parts.append(f"[{i}]adelay={delay_ms}|{delay_ms}[a{i}]")

    mix_inputs = "".join(f"[a{i}]" for i in range(len(cues)))
    filter_complex = (
        f"{';'.join(filter_parts)};{mix_inputs}amix=inputs={len(cues)}:duration=longest:dropout_transition=0,volume={len(cues)}[aout]"
    )

    cmd = [
        args.ffmpeg,
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "[aout]",
        "-t",
        f"{total_duration:.2f}",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(args.output),
    ]

    subprocess.run(cmd, check=True)
    print(f"Master audio track generated: {args.output}")


if __name__ == "__main__":
    main()
