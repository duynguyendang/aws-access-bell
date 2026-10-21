#!/usr/bin/env python3
import argparse
import asyncio
import os
import re
import sys
from pathlib import Path


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
        text = " ".join(lines[2:])
        cues.append({"id": cue_id, "time": lines[1], "text": text})
    return cues


def synthesize_polly(text: str, output_path: Path, voice_id: str = "Joanna"):
    import boto3

    region = os.getenv("AWS_REGION", "us-east-1")
    client = boto3.client("polly", region_name=region)
    resp = client.synthesize_speech(
        Engine="neural",
        OutputFormat="mp3",
        Text=text,
        VoiceId=voice_id,
    )
    if "AudioStream" in resp:
        with open(output_path, "wb") as f:
            f.write(resp["AudioStream"].read())
        return True
    return False


async def synthesize_edge_tts(text: str, output_path: Path, voice: str = "en-US-AriaNeural"):
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
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
        "--engine",
        choices=["polly", "edge-tts", "dry-run"],
        default="dry-run",
        help="Speech synthesis engine to use",
    )
    parser.add_argument(
        "--voice",
        default="Joanna",
        help="Voice identifier (e.g. Joanna/Matthew for Polly, en-US-AriaNeural for edge-tts)",
    )
    args = parser.parse_args()

    cues = parse_srt(args.srt)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loaded {len(cues)} cues from {args.srt}")

    if args.engine == "dry-run":
        for cue in cues:
            cue_file = args.output_dir / f"cue_{cue['id']}.txt"
            cue_file.write_text(f"[{cue['time']}]\n{cue['text']}\n", encoding="utf-8")
        print(f"Dry run complete. Text scripts exported to: {args.output_dir}")
        return

    if args.engine == "polly":
        for cue in cues:
            cue_audio = args.output_dir / f"cue_{cue['id']}.mp3"
            print(f"Synthesizing cue #{cue['id']} via AWS Polly...")
            try:
                synthesize_polly(cue["text"], cue_audio, voice_id=args.voice)
            except Exception as e:
                print(f"Polly error on cue #{cue['id']}: {e}", file=sys.stderr)
                sys.exit(1)
        print(f"All cues synthesized into: {args.output_dir}")

    elif args.engine == "edge-tts":
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            print(
                "Error: edge-tts is not installed in the active environment. Run `pip install edge-tts`.",
                file=sys.stderr,
            )
            sys.exit(1)

        for cue in cues:
            cue_audio = args.output_dir / f"cue_{cue['id']}.mp3"
            print(f"Synthesizing cue #{cue['id']} via Edge-TTS...")
            asyncio.run(synthesize_edge_tts(cue["text"], cue_audio, voice=args.voice))
        print(f"All cues synthesized into: {args.output_dir}")


if __name__ == "__main__":
    main()
