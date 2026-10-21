#!/usr/bin/env python3
import argparse
import asyncio
import os
import re
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
        cues.append(
            {
                "id": cue_id,
                "time": lines[1],
                "start": start_sec,
                "end": end_sec,
                "duration": end_sec - start_sec,
                "text": text,
            }
        )
    return cues


async def synthesize_edge_tts(text: str, output_path: Path, voice: str = "en-US-AriaNeural", rate: str = "+8%"):
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(output_path))
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate voiceover narration from SRT cues")
    parser.add_argument(
        "--srt",
        type=Path,
        default=Path("docs/accessbell-demo.srt"),
        help="Path to input SRT file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/internal/assets/narration_cues"),
        help="Directory to save per-cue audio files",
    )
    parser.add_argument(
        "--voice",
        default="en-US-AriaNeural",
        help="Edge-TTS voice identifier",
    )
    parser.add_argument(
        "--rate",
        default="+8%",
        help="Speech rate adjustment (e.g. +8%)",
    )
    args = parser.parse_args()

    cues = parse_srt(args.srt)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loaded {len(cues)} cues from {args.srt}")

    for cue in cues:
        cue_audio = args.output_dir / f"cue_{cue['id']}.mp3"
        print(f"Synthesizing cue #{cue['id']} ({cue['start']:.1f}s - {cue['end']:.1f}s)...")
        asyncio.run(synthesize_edge_tts(cue["text"], cue_audio, voice=args.voice, rate=args.rate))

    print(f"All {len(cues)} cues synthesized into: {args.output_dir}")


if __name__ == "__main__":
    main()
