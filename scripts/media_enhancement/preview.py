#!/usr/bin/env python3
"""Export a visibly labeled, palette-optimized GIF from a ready video derivative."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def export(folder):
    row = json.loads((folder / "job.json").read_text())
    if (
        row.get("state") != "ready"
        or row.get("kind") != "timelapse"
        or row.get("derivative") != "enhanced.mp4"
    ):
        raise ValueError("ready_video_required")
    source = folder / "enhanced.mp4"
    if hashlib.sha256(source.read_bytes()).hexdigest() != row["processing"]["sha256"]:
        raise ValueError("derivative_hash_mismatch")
    label = (
        "AI-interpolated preview"
        if row["processing"].get("synthetic_frames", 0)
        else "Neurally enhanced preview"
        if row["profile"] == "neural-video-2x"
        else "Processed preview"
    )
    target, temp = folder / "preview.gif", folder / "preview.partial.gif"
    filters = (
        "scale='min(720,iw)':-1,drawtext=text='"
        + label
        + "':x=8:y=8:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.65,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a"
    )
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(source),
                "-filter_complex_threads",
                "1",
                "-filter_complex",
                filters,
                "-fs",
                str(32 * 1024**2),
                "-loop",
                "0",
                "-y",
                str(temp),
            ],
            capture_output=True,
            timeout=45,
            check=True,
        )
        if not 0 < temp.stat().st_size < 32 * 1024**2:
            raise ValueError("preview_out_of_budget")
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(temp), "-f", "null", "-"],
            capture_output=True,
            timeout=15,
            check=True,
        )
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    print(export(parser.parse_args().folder))
