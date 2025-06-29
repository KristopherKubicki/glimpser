"""Utility functions for media file handling."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from flask import Response, request, send_file
from werkzeug.http import http_date

from app import config

FFMPEG = config.FFMPEG_PATH

# Precompiled regex for validating filenames: only letters, numbers,
# periods, hyphens and underscores.
ALLOWED_FILENAME_RE = re.compile(r"^[a-zA-Z0-9\.\-_]+?$")


@lru_cache(maxsize=256)
def _duration(p: str) -> float:
    """Return the duration of a video file using ffprobe."""
    out = subprocess.check_output(
        [
            FFMPEG.replace("ffmpeg", "ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            p,
        ]
    )
    return float(out.strip())


@lru_cache(maxsize=256)
def _probe(p: str, key: str):
    """Return ``key`` metadata for ``p`` via ffprobe."""
    out = subprocess.check_output(
        [
            FFMPEG.replace("ffmpeg", "ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            f"stream={key}",
            "-of",
            "json",
            p,
        ]
    )
    return json.loads(out)["streams"][0][key]


def send_conditional_file(
    source: Path | str | io.BytesIO, cache_seconds: int = 0, mimetype: str | None = None
) -> Response:
    """Return a file or buffer with ETag and caching headers."""

    if isinstance(source, (str, os.PathLike)):
        if mimetype:
            resp = send_file(source, conditional=True, mimetype=mimetype)
        else:
            resp = send_file(source, conditional=True)
        stat = os.stat(source)
        mtime = int(stat.st_mtime)
        size = stat.st_size
    else:
        if mimetype:
            resp = send_file(
                source, conditional=True, mimetype=mimetype, download_name="buffer"
            )
        else:
            resp = send_file(source, conditional=True, download_name="buffer")
        source.seek(0, os.SEEK_END)
        size = source.tell()
        source.seek(0)
        mtime = int(time.time())

    etag = f"{mtime}-{size}"
    resp.set_etag(etag)
    resp.headers["Cache-Control"] = f"public, max-age={cache_seconds}"
    resp.headers["Expires"] = http_date(time.time() + cache_seconds)
    resp.make_conditional(request)
    return resp


def _concat_copy(out: Path, parts: list[Path], clip_len: int = 120) -> bool:
    """Assemble a clip from segments using FFmpeg."""

    out_tmp = out.with_suffix(".tmp.mp4")
    ramroot = Path(tempfile.mkdtemp(dir=Path("/dev/shm")))
    fixed: list[Path] = []

    for p in parts:
        if p.name.startswith("final_"):
            fixed.append(p)
            continue
        dst = ramroot / f"{p.stem}_fix.mp4"
        try:
            subprocess.run(
                [
                    FFMPEG,
                    "-loglevel",
                    "quiet",
                    "-i",
                    p,
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    "-y",
                    dst,
                ],
                check=True,
                timeout=10,
            )
            fixed.append(dst)
        except subprocess.SubprocessError as e:
            logging.warning("skip broken %s (%s)", p, e)

    if not fixed:
        shutil.rmtree(ramroot)
        return False

    fixed.sort(key=os.path.getmtime)
    total = sum(_duration(p) for p in fixed)

    if total < clip_len:
        miss = clip_len - total
        ref = fixed[-1]
        first_clip = fixed[0]
        w, h = _probe(ref, "width"), _probe(ref, "height")
        fps_str = _probe(ref, "r_frame_rate")
        try:
            fps = float(Fraction(fps_str))
        except (ValueError, ZeroDivisionError):
            logging.warning("Invalid r_frame_rate %s, defaulting to 1", fps_str)
            fps = 1.0
        pad = ramroot / "pad_black.mp4"

        first_frame = ramroot / "first_frame.jpg"
        try:
            subprocess.run(
                [
                    FFMPEG,
                    "-loglevel",
                    "quiet",
                    "-i",
                    first_clip,
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    "-y",
                    first_frame,
                ],
                check=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            logging.error("FFmpeg frame extraction timed out after 20s")
            return False
        except subprocess.SubprocessError as exc:
            logging.error("FFmpeg frame extraction failed: %s", exc, exc_info=True)
            return False

        try:
            subprocess.run(
                [
                    FFMPEG,
                    "-loglevel",
                    "quiet",
                    "-loop",
                    "1",
                    "-i",
                    first_frame,
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=black@0.9:s={w}x{h}:r={fps}",
                    "-filter_complex",
                    f"[1:v]format=rgba,fade=t=out:st=0:d={miss}:alpha=1[ov];[0:v][ov]overlay",
                    "-t",
                    f"{miss:.3f}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-preset",
                    "ultrafast",
                    "-movflags",
                    "+faststart",
                    "-y",
                    pad,
                ],
                check=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            logging.error("FFmpeg pad generation timed out after 30s")
            return False
        except subprocess.SubprocessError as exc:
            logging.error("FFmpeg pad generation failed: %s", exc, exc_info=True)
            return False
        concat_parts = [pad] + fixed
    else:
        concat_parts = fixed

    concat_payload = (
        "\n".join(f"file 'file:{p.as_posix()}'" for p in concat_parts).encode() + b"\n"
    )

    total_duration = sum(_duration(p) for p in concat_parts)
    start_offset = max(0.0, total_duration - clip_len)

    cmd = [
        FFMPEG,
        "-loglevel",
        "warning",
        "-f",
        "concat",
        "-safe",
        "0",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        "pipe:0",
        "-ss",
        f"{start_offset:.3f}",
        "-t",
        str(clip_len),
        "-c",
        "copy",
        "-reset_timestamps",
        "1",
        "-movflags",
        "+faststart",
        "-y",
        out_tmp,
    ]

    try:
        subprocess.run(cmd, input=concat_payload, timeout=30, check=True)
        out_tmp.rename(out)
        return True
    except subprocess.TimeoutExpired:
        logging.error("FFmpeg concat timed out after 30s")
        out_tmp.unlink(missing_ok=True)
        return False
    except subprocess.SubprocessError as exc:
        logging.error("FFmpeg concat failed: %s", exc, exc_info=True)
        out_tmp.unlink(missing_ok=True)
        return False
    finally:
        shutil.rmtree(ramroot, ignore_errors=True)


def allowed_filename(filename: str) -> bool:
    """Return ``True`` when ``filename`` contains only safe characters."""

    if ".." in filename:
        return False

    if ALLOWED_FILENAME_RE.fullmatch(filename):
        return True

    return False


__all__ = [
    "ALLOWED_FILENAME_RE",
    "allowed_filename",
    "send_conditional_file",
    "_concat_copy",
    "_duration",
    "_probe",
]
