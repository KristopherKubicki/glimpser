"""Review bounded OTA windows and atomically publish only grounded personal clips."""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.feed_tv.core import ROOT, capacity, lock, read, status, write

SSH = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=8",
    "-i",
    str(Path.home() / ".ssh/id_ed25519_netops_codex"),
    "kristopher@192.168.40.150",
    "python3",
    "/home/kristopher/.local/lib/glimpser-feed-tv/review_worker.py",
]


def normalized(text):
    return " ".join(re.findall(r"\w+", text.lower()))


def grounded(review, transcript):
    if not isinstance(review, dict):
        return False
    quote = review.get("evidence_quote", "")
    return (
        review.get("usable") is True
        and review.get("category") in {"news", "weather", "public_affairs"}
        and isinstance(review.get("relevance"), int)
        and 3 <= review["relevance"] <= 5
        and isinstance(review.get("confidence"), (int, float))
        and 0.85 <= review["confidence"] <= 1
        and isinstance(quote, str)
        and len(normalized(quote)) >= 20
        and normalized(quote) in normalized(transcript)
        and all(
            isinstance(review.get(k), str) and len(review[k]) <= 240
            for k in ["title", "observation", "limitations"]
        )
        and len(normalized(transcript)) >= 80
    )


def shingles(text):
    words = normalized(text).split()
    return {" ".join(words[i : i + 5]) for i in range(max(0, len(words) - 4))}


def duplicate(transcript, existing):
    tokens = shingles(transcript)
    if not tokens:
        return False
    for prior in existing:
        other = shingles(prior)
        if other and len(tokens & other) / len(tokens | other) > 0.75:
            return True
    return False


def probe(source):
    p = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    data = json.loads(p.stdout)
    duration = float(data["format"]["duration"])
    if not 20 <= duration <= 330 or not any(
        s.get("codec_type") == "video" for s in data.get("streams", [])
    ):
        raise ValueError("unusable_media")
    return duration


def prepare(folder, duration):
    source = folder / "source.ts"
    sheet = Image.new("RGB", (960, 580), "#050a10")
    frames = []
    for index in range(6):
        stamp = min(duration - 1, (index + 0.5) * duration / 6)
        frame = folder / f"frame-{index}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-ss",
                str(stamp),
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:-2",
                "-y",
                str(frame),
            ],
            capture_output=True,
            timeout=15,
            check=True,
        )
        with Image.open(frame) as image:
            tile = ImageOps.contain(image.convert("RGB"), (320, 240))
            x, y = index % 3 * 320, index // 3 * 290
            sheet.paste(tile, (x + (320 - tile.width) // 2, y))
            ImageDraw.Draw(sheet).text(
                (x + 8, y + 245), f"{index + 1} · {stamp:.0f}s", fill="white"
            )
        frames.append(frame)
    sheet.save(folder / "contact.jpg", quality=85)
    # Decoder-extracted A53 captions; no ASR service or credential dependency.
    subtitle = folder / "captions.srt"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"movie={source}[out0+subcc]",
            "-map",
            "0:s:0",
            "-t",
            str(duration),
            "-y",
            str(subtitle),
        ],
        capture_output=True,
        timeout=60,
    )
    text = subtitle.read_text(errors="replace")[:40000] if subtitle.exists() else ""
    text = re.sub(r"(?m)^\d+\s*$|^\d\d:\d\d:.*$", "", text)
    return " ".join(text.split())


def review_one(root=ROOT):
    with lock(root, "review"):
        for folder in sorted((root / "buffer").glob("*")):
            row = read(folder / "capture.json")
            if (
                folder.is_symlink()
                or not row.get("complete")
                or row.get("selection") != "unreviewed"
                or time.time() < row.get("retry_at", 0)
            ):
                continue
            if not (folder / "source.ts").is_file() or not capacity(root):
                status(root, "review", "capacity_or_source_guard")
                return
            active = folder / "reviewing"
            active.touch()
            phase = "probe"
            try:
                duration = probe(folder / "source.ts")
                phase = "decode"
                transcript = prepare(folder, duration)
                if len(normalized(transcript)) < 80:
                    row["selection"] = "needs_captions"
                    write(folder / "capture.json", row)
                    status(
                        root,
                        "review",
                        "held",
                        reason="insufficient_captions",
                        capture_id=row["id"],
                    )
                    return
                status(root, "review", "reviewing", capture_id=row["id"])
                request = {
                    "station": row["station"],
                    "transcript": transcript,
                    "image": base64.b64encode(
                        (folder / "contact.jpg").read_bytes()
                    ).decode(),
                }
                phase = "personal_spark"
                result = subprocess.run(
                    SSH,
                    input=json.dumps(request),
                    capture_output=True,
                    text=True,
                    timeout=270,
                    check=True,
                )
                decision = json.loads(result.stdout)
                write(folder / "review.json", decision)
                prior = [read(p) for p in (root / "clips").glob("*/clip.json")]
                repeats = duplicate(
                    transcript,
                    [
                        p.get("transcript", "")
                        for p in prior
                        if p.get("recorded_at", 0) > time.time() - 21600
                    ],
                )
                if grounded(decision, transcript) and not repeats:
                    phase = "publish"
                    publish(root, folder, row, decision, transcript, duration)
                    row["selection"] = "published"
                else:
                    row["selection"] = "duplicate" if repeats else "rejected"
                write(folder / "capture.json", row)
                status(root, "review", row["selection"], capture_id=row["id"])
            except (
                subprocess.SubprocessError,
                OSError,
                ValueError,
                KeyError,
                TypeError,
            ) as error:
                if (
                    phase == "probe"
                    and isinstance(error, ValueError)
                    and str(error) == "unusable_media"
                ):
                    row["selection"] = "short_or_invalid_media"
                    write(folder / "capture.json", row)
                    status(
                        root,
                        "review",
                        "held",
                        capture_id=row["id"],
                        reason=row["selection"],
                    )
                    return
                reason = type(error).__name__
                busy = phase == "personal_spark" and "personal_spark_busy_defer" in str(
                    getattr(error, "stderr", "")
                )
                if busy:
                    reason = "personal_spark_busy"
                    delay = 120
                else:
                    row["attempts"] = row.get("attempts", 0) + 1
                    delay = min(7200, 300 * 2 ** min(row["attempts"], 4))
                row["retry_at"] = time.time() + delay
                write(folder / "capture.json", row)
                status(
                    root,
                    "review",
                    "deferred",
                    capture_id=row["id"],
                    phase=phase,
                    reason=reason,
                )
            finally:
                active.unlink(missing_ok=True)
            return
        status(root, "review", "idle")


def publish(root, folder, row, decision, transcript, duration):
    dest = root / "clips" / row["id"]
    if (dest / "clip.json").exists():
        return
    stage = dest.with_name(dest.name + ".partial")
    stage.mkdir(parents=True, exist_ok=True)
    # Preserve source bytes once; the viewing derivative is separate.
    source = folder / "source.ts"
    master = stage / "source.ts"
    if not master.exists():
        os.link(source, master)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "yadif=0,scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-y",
            str(stage / "clip.mp4"),
        ],
        capture_output=True,
        timeout=240,
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(folder / "captions.srt"),
            "-y",
            str(stage / "captions.vtt"),
        ],
        capture_output=True,
        timeout=10,
        check=True,
    )
    actual = probe(stage / "clip.mp4")
    if actual < duration * 0.9:
        raise ValueError("incomplete_derivative")
    shutil.copy2(folder / "contact.jpg", stage / "poster.jpg")
    write(
        stage / "clip.json",
        {
            "id": row["id"],
            "scope": "personal",
            "station": row["station"],
            "channel": row["channel"],
            "recorded_at": row["started"],
            "published_at": time.time(),
            "duration": actual,
            "review": decision,
            "transcript": transcript,
            "master_sha256": row.get("sha256"),
            "label": "Recorded excerpt · story boundaries unverified",
        },
    )
    os.replace(stage, dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    review_one(args.root)
