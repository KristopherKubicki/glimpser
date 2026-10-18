#!/usr/bin/env python3
"""Saved-footage archive, Spark editorial review and atomic video editions."""

import argparse
import base64
import collections
import datetime as dt
import fcntl
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from contextlib import ExitStack
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence, ImageStat

TZ = ZoneInfo("America/Chicago")
UTC = dt.timezone.utc
CAMERAS = {
    "FrontDoor": "Knox",
    "Driveway": "Knox",
    "Street": "Knox",
    "Garden": "Knox",
    "Backyard": "Knox",
    "Garage": "Knox",
    "Walkway": "Knox",
    "BeachDriveway": "Beach",
    "BeachBioswale": "Beach",
    "BeachShore": "Beach",
    "BeachSouthJetty": "Beach",
    "BeachMapleTree": "Beach",
    "BeachPathway": "Beach",
    "Beach_Google_Front_Door": "Beach",
    "ArgyleEntryFisheye": "Argyle",
    "Front_door_doorbell": "Argyle",
    "Showroom_Entrance": "Argyle",
    "Halsted023": "Halsted",
    "Halsted036": "Halsted",
    "Argyle400": "Argyle",
    "Tesla-Front": "Tesla",
    "Tesla-Rear": "Tesla",
    "Tesla-Left": "Tesla",
    "Tesla-Right": "Tesla",
}
ROOT = Path.home() / ".local/share/glimpser-magazine"
DATA = Path("/home/kristopher/code/glimpser/data")
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
    "/home/kristopher/.local/lib/glimpser-magazine/review.py",
]


def write_json(path, value):
    """Publish complete metadata with a same-filesystem rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    os.replace(temporary, path)


def periods(now, started):
    """Completed calendar periods, with weekly preparation two hours before 8AM."""
    local = now.astimezone(TZ)
    saturday = (local - dt.timedelta(days=(local.weekday() - 5) % 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if saturday > local:
        saturday -= dt.timedelta(days=7)
    month = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    quarter = month.replace(month=1 + 3 * ((local.month - 1) // 3))
    year = month.replace(month=1)
    result = []
    for kind, end, months in [
        ("weekly", saturday, 0),
        ("monthly", month, 1),
        ("quarterly", quarter, 3),
        ("yearly", year, 12),
    ]:
        ready = end.replace(hour=6)
        if ready > local or ready < started.astimezone(TZ):
            continue
        if months:
            index = end.year * 12 + end.month - 1 - months
            start = end.replace(year=index // 12, month=index % 12 + 1)
        else:
            start = end - dt.timedelta(days=7)
        result.append(
            {
                "id": f"{kind}-{end.date()}",
                "kind": kind,
                "start": start.timestamp(),
                "end": end.timestamp(),
            }
        )
    return result


def evenly(items, limit):
    if len(items) <= limit:
        return items
    return [items[round(i * (len(items) - 1) / (limit - 1))] for i in range(limit)]


def quality(image):
    """Reject near-blank imagery; editorial quality is reviewed separately."""
    gray = image.convert("L").resize((160, 90))
    stats = ImageStat.Stat(gray)
    return 10 < stats.mean[0] < 243 and stats.stddev[0] > 12


def collect_events(root, data, now):
    """Preserve already-recorded event replays with their original frame timing."""
    count = 0
    for camera, site in CAMERAS.items():
        for path in (data / "event_buffer" / camera / "events").glob("*.gif"):
            match = re.fullmatch(re.escape(camera) + r"_(\d+)\.gif", path.name)
            if not match or path.is_symlink() or path.stat().st_size > 32_000_000:
                continue
            event_at = int(match[1]) / 1000
            if not now - 86400 <= event_at <= now:
                continue
            identity = f"{camera}-event-{match[1]}"
            dest = root / "candidates" / identity
            if (dest / "candidate.json").exists():
                continue
            with Image.open(path) as video:
                if video.n_frames > 120:
                    continue
                frames = []
                for frame in ImageSequence.Iterator(video):
                    frame = frame.copy()
                    frame.thumbnail((1280, 720))
                    frames.append(
                        (
                            frame.convert("RGB"),
                            max(0.02, frame.info.get("duration", 100) / 1000),
                        )
                    )
            duration = sum(seconds for _, seconds in frames)
            if len(frames) < 4 or not 2 <= duration <= 45:
                continue
            if sum(quality(image) for image, _ in frames) / len(frames) < 0.8:
                continue
            stage = dest.with_name(identity + ".partial")
            stage.mkdir(exist_ok=True)
            records = []
            for index, (image, seconds) in enumerate(frames):
                image.thumbnail((1920, 1080))
                name = f"frame-{index:03}.jpg"
                image.save(stage / name, quality=88)
                records.append(
                    {
                        "file": name,
                        "source": path.name,
                        "source_utc": event_at,
                        "duration": seconds,
                        "sha256": hashlib.sha256(
                            (stage / name).read_bytes()
                        ).hexdigest(),
                    }
                )
            write_json(
                stage / "candidate.json",
                {
                    "id": identity,
                    "camera": camera,
                    "site": site,
                    "kind": "event",
                    "start": event_at,
                    "end": event_at,
                    "duration": duration,
                    "frames": records,
                    "timing_note": "Timestamp identifies the event trigger; replay retains recorded frame timing.",
                },
            )
            os.replace(stage, dest)
            count += 1
    return count


def retain_keepers(root, now):
    """Do not expire review proxies while a reviewer or renderer is using them."""
    with ExitStack() as stack:
        try:
            for mode in ("review", "produce", "pilot"):
                handle = stack.enter_context((root / (mode + ".lock")).open("a"))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return _retain_keepers(root, now)


def _retain_keepers(root, now):
    """Expire only this job's review proxies; preserve published and monthly keepers."""
    protected = set()
    for manifest in (root / "editions").glob("*/manifest.json"):
        protected.update(
            c["candidate"] for c in json.loads(manifest.read_text())["chapters"]
        )
    reviewed = []
    groups = collections.defaultdict(list)
    for path in (root / "candidates").glob("*/candidate.json"):
        review_path = path.with_name("review.json")
        if not review_path.exists() or path.parent.is_symlink():
            continue
        row = json.loads(path.read_text())
        if row.get("id") != path.parent.name or row.get("camera") not in CAMERAS:
            continue
        review = json.loads(review_path.read_text())
        reviewed.append((path, row, review))
        if review.get("usable"):
            month = dt.datetime.fromtimestamp(row["start"], TZ).strftime("%Y-%m")
            groups[(row["camera"], month)].append(
                (
                    review["interest"] * 2 + review["aesthetic"] + review["change"],
                    row["id"],
                )
            )
    for rows in groups.values():
        protected.update(identity for _, identity in sorted(rows, reverse=True)[:3])
    removed = 0
    for path, row, review in reviewed:
        lifetime = 45 * 86400 if review.get("usable") else 7 * 86400
        if row["id"] not in protected and now - row["end"] > lifetime:
            shutil.rmtree(path.parent)
            removed += 1
    return removed


def collect(root, data, now):
    """Preserve bounded coherent sequences, without contacting a camera."""
    candidates = root / "candidates"
    candidates.mkdir(parents=True, exist_ok=True)
    retired = retain_keepers(root, now)
    used = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if used > 30 * 1024**3 or shutil.disk_usage(root).free < 15 * 1024**3:
        raise RuntimeError("archive_capacity_guard")
    count = 0
    for camera, site in CAMERAS.items():
        groups = collections.defaultdict(list)
        folder = data / "screenshots" / camera
        for path in folder.glob(camera + "_*.png"):
            match = re.fullmatch(re.escape(camera) + r"_(\d{14})\.png", path.name)
            if not match or path.is_symlink():
                continue
            stamp = (
                dt.datetime.strptime(match[1], "%Y%m%d%H%M%S")
                .replace(tzinfo=UTC)
                .timestamp()
            )
            if not now - 86400 <= stamp <= now:
                continue
            # Only closed local three-hour windows: do not freeze a candidate after its first frame.
            local = dt.datetime.fromtimestamp(stamp, TZ)
            window = local.replace(
                hour=(local.hour // 3) * 3, minute=0, second=0, microsecond=0
            )
            bucket = int(window.timestamp())
            if (window + dt.timedelta(hours=3)).timestamp() > now:
                continue
            groups[bucket].append((stamp, path))
        for bucket, frames in groups.items():
            identity = f"{camera}-{bucket}"
            dest = candidates / identity
            if (dest / "candidate.json").exists():
                continue
            stage = candidates / (identity + ".partial")
            stage.mkdir(exist_ok=True)
            accepted, hashes = [], set()
            for stamp, path in evenly(sorted(frames), 24):
                clean = path.with_name(path.name + ".clean.png")
                source = clean if clean.is_file() and not clean.is_symlink() else path
                try:
                    with Image.open(source) as image:
                        image = ImageOps.exif_transpose(image).convert("RGB")
                        if not quality(image):
                            continue
                        image.thumbnail((1920, 1080))
                        proxy = io.BytesIO()
                        image.save(proxy, format="JPEG", quality=88)
                        digest = hashlib.sha256(proxy.getvalue()).hexdigest()
                        if digest in hashes:
                            continue
                        hashes.add(digest)
                        name = f"frame-{len(accepted):03}.jpg"
                        (stage / name).write_bytes(proxy.getvalue())
                        accepted.append(
                            {
                                "file": name,
                                "source": path.name,
                                "source_utc": stamp,
                                "sha256": digest,
                            }
                        )
                except (OSError, ValueError):
                    continue
            if not accepted:
                shutil.rmtree(stage)
                continue
            kind = "timelapse"
            if (
                len(accepted) < 4
                or accepted[-1]["source_utc"] - accepted[0]["source_utc"] < 30
            ):
                kind = "still"
                accepted = [accepted[len(accepted) // 2]]
            record = {
                "id": identity,
                "camera": camera,
                "site": site,
                "kind": kind,
                "start": accepted[0]["source_utc"],
                "end": accepted[-1]["source_utc"],
                "frames": accepted,
            }
            write_json(stage / "candidate.json", record)
            os.replace(stage, dest)
            count += 1
    count += collect_events(root, data, now)
    # Keep structured observations independently of film selections.
    for source in ["glimpser-home-digest", "glimpser-eod-digest"]:
        for report in (Path.home() / ".local/state" / source).glob("????-??-??.json"):
            target = root / "observations" / source / report.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report, target)
    write_json(
        root / "collection-status.json",
        {
            "checked_at": now,
            "new_candidates": count,
            "archive_bytes_before": used,
            "expired_review_proxies": retired,
        },
    )
    return count


def review(root, limit=24):
    """Review chronological contact sheets on the existing personal Spark."""
    stats = {"reviewed": 0, "attempted": 0, "failed": 0, "deferred": False}

    def progress(state):
        write_json(
            root / "review-status.json",
            {
                "checked_at": dt.datetime.now(UTC).isoformat(),
                "state": state,
                "result": dict(stats),
            },
        )

    progress("running")
    queues = collections.defaultdict(list)
    for path in sorted((root / "candidates").glob("*/candidate.json"), reverse=True):
        if (
            not path.with_name("review.json").exists()
            or json.loads(path.with_name("review.json").read_text()).get(
                "review_version"
            )
            != 2
        ):
            record = json.loads(path.read_text())
            queues[record["site"]].append(path)
    pending = []
    while any(queues.values()):
        for site in sorted(queues):
            if queues[site]:
                pending.append(queues[site].pop(0))
    for path in pending:
        if stats["attempted"] >= limit:
            break
        failure_path = path.with_name("review-failure.json")
        previous = json.loads(failure_path.read_text()) if failure_path.exists() else {}
        if previous.get("retry_at", 0) > time.time():
            continue
        output = path.with_name("review.json")
        if (
            output.exists()
            and json.loads(output.read_text()).get("review_version") == 2
        ):
            continue
        row = json.loads(path.read_text())
        sheet = Image.new("RGB", (1200, 750), "#08121c")
        for index, frame in enumerate(evenly(row["frames"], 6)):
            with Image.open(path.parent / frame["file"]) as image:
                tile = ImageOps.contain(image, (400, 220))
                x, y = (index % 3) * 400, (index // 3) * 375
                sheet.paste(tile, (x + (400 - tile.width) // 2, y))
                ImageDraw.Draw(sheet).text(
                    (x + 8, y + 230),
                    f"{index + 1}: "
                    + dt.datetime.fromtimestamp(frame["source_utc"], TZ).strftime(
                        "%b %d %H:%M:%S"
                    ),
                    fill="white",
                )
        encoded = io.BytesIO()
        sheet.save(encoded, format="JPEG", quality=85)
        request = {
            "image": base64.b64encode(encoded.getvalue()).decode(),
            "camera": row["camera"],
            "site": row["site"],
            "kind": row["kind"],
        }
        stats["attempted"] += 1
        try:
            process = subprocess.run(
                SSH,
                input=json.dumps(request),
                text=True,
                capture_output=True,
                timeout=300,
            )
            if process.returncode:
                if "personal_spark_busy_defer" in process.stderr:
                    stats["deferred"] = True
                    break
                category = next(
                    (
                        name
                        for name in (
                            "incomplete_editorial_review",
                            "JSONDecodeError",
                            "HTTPError",
                            "TimeoutError",
                        )
                        if name in process.stderr
                    ),
                    "personal_spark_review_unavailable",
                )
                raise RuntimeError(category)
            response = json.loads(process.stdout)
            if not isinstance(response, dict):
                raise ValueError("invalid_editorial_review")
            if not isinstance(response.get("usable"), bool):
                raise ValueError("invalid_editorial_review")
            for key in ["aesthetic", "interest", "change"]:
                value = response.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 <= value <= 5
                ):
                    raise ValueError("invalid_editorial_score")
            if response.get("review_version") != 2 or not isinstance(
                response.get("quality_issues"), list
            ):
                raise ValueError("incomplete_quality_review")
            for key in ("observation", "limitations", "reason"):
                if not isinstance(response.get(key), str):
                    raise ValueError("invalid_editorial_text")
            if response["quality_issues"]:
                response["usable"] = False
            response["reviewed_at"] = time.time()
            write_json(output, response)
        except (subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            attempts = previous.get("attempts", 0) + 1
            category = type(exc).__name__
            if isinstance(exc, RuntimeError):
                category = str(exc)
            write_json(
                failure_path,
                {
                    "category": category,
                    "attempts": attempts,
                    "failed_at": time.time(),
                    "retry_at": time.time()
                    + min(86400, 3600 * 4 ** min(attempts - 1, 3)),
                },
            )
            stats["failed"] += 1
            progress("running")
            continue
        failure_path.unlink(missing_ok=True)
        stats["reviewed"] += 1
        progress("running")
    progress("deferred" if stats["deferred"] else "complete")
    return stats


def select(candidates, period, limit=30):
    """Require reviewed usable footage; limit repetition while retaining ranked interest."""
    eligible = [
        r
        for r in candidates
        if r["start"] >= period["start"]
        and r["end"] < period["end"]
        and r["review"].get("usable")
        and r["review"].get("review_version") == 2
        and (r["review"]["interest"] >= 3 or r["review"]["aesthetic"] >= 4)
    ]
    eligible.sort(
        key=lambda r: (
            2 * r["review"]["interest"]
            + r["review"]["aesthetic"]
            + r["review"]["change"]
        ),
        reverse=True,
    )
    picked = []
    camera_counts = collections.Counter()
    site_counts = collections.Counter()
    days = set()
    for row in eligible:
        key = (row["camera"], dt.datetime.fromtimestamp(row["start"], TZ).date())
        if (
            (
                row.get("kind") == "still"
                and sum(r.get("kind") == "still" for r in picked)
                >= min(3, max(1, len(eligible) // 3))
            )
            or camera_counts[row["camera"]] >= 3
            or site_counts[row["site"]] >= max(4, limit // 3)
            or key in days
        ):
            continue
        picked.append(row)
        camera_counts[row["camera"]] += 1
        site_counts[row["site"]] += 1
        days.add(key)
        if len(picked) >= limit:
            break
    # Chapters by site, with the strongest shot opening each chapter.
    site_order = list(dict.fromkeys(r["site"] for r in picked))
    return sorted(picked, key=lambda r: site_order.index(r["site"]))


def run(command, timeout=240):
    subprocess.run(command, check=True, capture_output=True, timeout=timeout)


def render(root, period):
    """Render reviewed material privately; publish only a validated, complete edition."""
    target = root / "editions" / period["id"]
    if (target / "manifest.json").exists():
        return "already_published"
    candidates = []
    for path in (root / "candidates").glob("*/candidate.json"):
        if path.with_name("review.json").exists():
            row = json.loads(path.read_text())
            row["review"] = json.loads(path.with_name("review.json").read_text())
            candidates.append(row)
    selected = select(
        candidates,
        period,
        {"weekly": 48, "monthly": 80, "quarterly": 100, "yearly": 140}.get(
            period["kind"], 30
        ),
    )
    if len(selected) < 3:
        return "insufficient_reviewed_footage"
    stage = root / "rendering" / period["id"]
    stage.mkdir(parents=True, exist_ok=True)
    intro = Image.new("RGB", (1280, 720), "#08121c")
    draw = ImageDraw.Draw(intro)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    draw.text(
        (72, 130),
        "GLIMPSER  /  THE VIDEO MAGAZINE",
        font=ImageFont.truetype(font, 24),
        fill="#a1d9cc",
    )
    draw.text((72, 240), "In Review", font=ImageFont.truetype(font, 76), fill="#dae5ed")
    draw.text(
        (72, 365), period["id"], font=ImageFont.truetype(font, 32), fill="#adbfcd"
    )
    draw.text(
        (72, 470),
        "Selected moments and visible changes",
        font=ImageFont.truetype(font, 28),
        fill="#dae5ed",
    )
    draw.text(
        (72, 525),
        "Saved footage · Source dates shown · Model-assisted observations",
        font=ImageFont.truetype(font, 22),
        fill="#adbfcd",
    )
    intro.save(stage / "intro.png")
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(stage / "intro.png"),
            "-t",
            "5",
            "-vf",
            "fps=30,fade=t=in:st=0:d=0.6,fade=t=out:st=4.4:d=0.6",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            str(stage / "intro.mp4"),
        ]
    )
    chapters = []
    for index, row in enumerate(selected):
        folder = root / "candidates" / row["id"]
        listing = stage / f"{index:03}.txt"
        lines = []
        # Every source frame appears once in source order; the label names elapsed source time.
        duration = (
            row.get("duration")
            if row["kind"] == "event"
            else max(8, min(14, len(row["frames"]) * 0.5))
        )
        for frame in row["frames"]:
            lines += [
                f"file '{folder / frame['file']}'",
                f"duration {frame.get('duration', duration / len(row['frames'])):.6f}",
            ]
        lines += [f"file '{folder / row['frames'][-1]['file']}'"]
        listing.write_text("\n".join(lines) + "\n")
        label = stage / f"{index:03}-label.txt"
        start = dt.datetime.fromtimestamp(row["start"], TZ)
        elapsed = round((row["end"] - row["start"]) / 60)
        timing = (
            "Still photograph"
            if row["kind"] == "still"
            else "Recorded event replay"
            if row["kind"] == "event"
            else f"Timelapse: {elapsed} minutes condensed"
        )
        label.write_text(
            f"{row['site']} | {row['camera']}\n{start:%b %d, %Y %H:%M %Z} | {timing}"
        )
        observation = stage / f"{index:03}-observation.txt"
        observation.write_text(
            textwrap.fill(str(row["review"].get("observation", ""))[:180], width=85)
        )
        output = stage / f"{index:03}.mp4"
        vf = (
            "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x08121c,setsar=1,fps=30,"
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile={label}:fontcolor=white:fontsize=22:box=1:boxcolor=black@0.65:boxborderw=12:x=24:y=h-86,"
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile={observation}:expansion=none:fontcolor=white:fontsize=24:box=1:boxcolor=black@0.65:boxborderw=12:x=24:y=24,"
            f"fade=t=in:st=0:d=0.6,fade=t=out:st={duration - 0.6}:d=0.6"
        )
        run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-vf",
                vf,
                "-t",
                str(duration),
                "-an",
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ]
        )
        chapters.append(
            {
                "camera": row["camera"],
                "site": row["site"],
                "candidate": row["id"],
                "kind": row["kind"],
                "source_start": row["start"],
                "source_end": row["end"],
                "duration": duration,
                "review": row["review"],
            }
        )
    listing = stage / "concat.txt"
    listing.write_text(
        f"file '{stage / 'intro.mp4'}'\n"
        + "".join(f"file '{stage / f'{i:03}.mp4'}'\n" for i in range(len(selected)))
    )
    film = stage / "film.mp4"
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(film),
        ],
        600,
    )
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(film),
            ],
            timeout=30,
        )
    )
    expected = 5 + sum(c["duration"] for c in chapters)
    cursor = 5
    for chapter in chapters:
        chapter["start_seconds"] = cursor
        cursor += chapter["duration"]
    if (
        abs(float(probe["format"]["duration"]) - expected) > 2
        or probe["streams"][0]["codec_name"] != "h264"
    ):
        raise RuntimeError("render_validation_failed")
    run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(film), "-f", "null", "-"], 600)
    manifest = {
        **period,
        "published_at": time.time(),
        "duration": expected,
        "chapters": chapters,
        "coverage": "Selected saved captures only; not continuous surveillance. Timelapses are sped up. Observations are model-assisted and require source verification.",
        "available_source_dates": sorted(
            {
                dt.datetime.fromtimestamp(r["start"], TZ).date().isoformat()
                for r in candidates
                if period["start"] <= r["start"] < period["end"]
            }
        ),
        "sha256": hashlib.file_digest(film.open("rb"), "sha256").hexdigest(),
    }
    archive = stage / "publish"
    archive.mkdir(exist_ok=True)
    shutil.copy2(film, archive / "film.mp4")
    write_json(archive / "manifest.json", manifest)
    content = f"<h1>{html.escape(period['id'])}</h1><p>{html.escape(manifest['coverage'])}</p>"
    content += (
        "<p>Dates with archived source candidates: "
        + html.escape(", ".join(manifest["available_source_dates"]))
        + ". Dates not listed have no source coverage in this archive.</p>"
    )
    for c in chapters:
        content += f"<h2>{html.escape(c['site'] + ' · ' + c['camera'])}</h2><p>{html.escape(str(c['review'].get('observation', '')))}</p><p>{html.escape(str(c['review'].get('limitations', '')))}</p>"
    content += "<h2>Coverage</h2><p>Only the selected source windows listed in the manifest were reviewed for this film. No claim of all-clear or complete period coverage is made.</p>"
    observations = []
    for report in sorted((root / "observations").glob("*/*.json")):
        try:
            day = dt.date.fromisoformat(report.stem)
            if (
                dt.datetime.fromtimestamp(period["start"], TZ).date()
                <= day
                < dt.datetime.fromtimestamp(period["end"], TZ).date()
            ):
                original = json.loads(report.read_text())
                observations.append(
                    {
                        "source": report.parent.name,
                        "date": report.stem,
                        "evidence": original.get("evidence", {}),
                    }
                )
        except (ValueError, OSError):
            continue
    write_json(archive / "observations.json", observations)
    if observations:
        content += "<h2>Daily review notebook</h2><p>These retained daily reviews have their own sampling windows; they are additional context, not claims about footage in the film.</p>"
        for report in observations:
            content += (
                "<details><summary>"
                + html.escape(report["source"] + " · " + report["date"])
                + "</summary><pre>"
                + html.escape(json.dumps(report["evidence"], indent=2))
                + "</pre></details>"
            )
    (archive / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Video magazine</title>' + content
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(archive, target)
    shutil.rmtree(stage)
    return "published"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["collect", "review", "produce", "pilot"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args()
    root = args.root
    root.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    with (root / (args.mode + ".lock")).open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = dt.datetime.now(UTC)
        config = root / "config.json"
        if not config.exists():
            write_json(config, {"started_at": now.isoformat()})
        if args.mode == "collect":
            result = {"new_candidates": collect(root, args.data, now.timestamp())}
        elif args.mode == "review":
            result = review(root, args.limit)
        else:
            started = dt.datetime.fromisoformat(
                json.loads(config.read_text())["started_at"]
            )
            due = periods(now, started)
            if args.mode == "pilot":
                due = [
                    {
                        "id": "pilot-" + now.astimezone(TZ).strftime("%Y%m%d"),
                        "kind": "pilot",
                        "start": (now - dt.timedelta(days=7)).timestamp(),
                        "end": now.timestamp(),
                    }
                ]
            result = {p["id"]: render(root, p) for p in due}
        if args.mode != "review":
            write_json(
                root / (args.mode + "-status.json"),
                {"checked_at": now.isoformat(), "result": result},
            )
        print(json.dumps(result))


if __name__ == "__main__":
    main()
