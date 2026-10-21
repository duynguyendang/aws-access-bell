#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def probe_with_ffprobe(video_path: Path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=codec_type,width,height,codec_name",
        "-of",
        "default=noprint_wrappers=1",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    metadata = {}
    for line in res.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            metadata[k.strip()] = v.strip()
    return metadata


def parse_mp4_duration(video_path: Path):
    data = video_path.read_bytes()
    mvhd_idx = data.find(b"mvhd")
    if mvhd_idx == -1:
        return None
    version = data[mvhd_idx + 4]
    offset = mvhd_idx + 8
    if version == 0:
        timescale = int.from_bytes(data[offset + 8 : offset + 12], "big")
        duration = int.from_bytes(data[offset + 12 : offset + 16], "big")
    else:
        timescale = int.from_bytes(data[offset + 16 : offset + 20], "big")
        duration = int.from_bytes(data[offset + 20 : offset + 28], "big")
    if timescale > 0:
        return duration / timescale
    return None


def main():
    parser = argparse.ArgumentParser(description="Verify demo video specifications")
    parser.add_argument("video", type=Path, help="Path to MP4 video file")
    parser.add_argument(
        "--max-duration",
        type=float,
        default=180.0,
        help="Maximum allowable duration in seconds",
    )
    args = parser.parse_args()

    if not args.video.exists():
        print(f"Error: Video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    file_size_mb = args.video.stat().st_size / (1024 * 1024)
    duration = None
    width = None
    height = None

    if shutil.which("ffprobe"):
        try:
            meta = probe_with_ffprobe(args.video)
            duration = float(meta.get("duration", 0))
            width = meta.get("width")
            height = meta.get("height")
        except Exception:
            pass

    if duration is None:
        duration = parse_mp4_duration(args.video)

    is_internal = "docs/internal" in str(args.video.resolve()) or "internal" in args.video.parts

    print("=== AccessBell Video Specification Check ===")
    print(f"File: {args.video}")
    print(f"Size: {file_size_mb:.2f} MB")
    if width and height:
        print(f"Dimensions: {width}x{height}")
    if duration is not None:
        mins = int(duration // 60)
        secs = int(duration % 60)
        print(f"Duration: {mins:02d}:{secs:02d} ({duration:.2f}s)")
    else:
        print("Duration: [Unable to determine without ffprobe]")

    print(f"Internal Storage Compliance: {'PASS' if is_internal else 'FAIL (Must be in docs/internal/)'}")

    passed = True
    if duration is not None:
        if duration > args.max_duration:
            print(f"FAIL: Duration {duration:.1f}s exceeds maximum limit of {args.max_duration}s.")
            passed = False
        else:
            print(f"PASS: Duration is within limit (≤ {args.max_duration}s).")

    if not is_internal:
        print("FAIL: Video must be stored inside docs/internal/ to prevent git tracking.")
        passed = False

    if not passed:
        sys.exit(1)
    print("ALL CHECKS PASSED.")


if __name__ == "__main__":
    main()
