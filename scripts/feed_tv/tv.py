"""Spare-capacity personal OTA capture; no forced tuning or work ad collection."""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.feed_tv.core import ROOT, capacity, clean_buffer, lock, read, status, write

TZ = ZoneInfo("America/Chicago")
DEFAULT_CHANNELS = ["9.1", "7.1", "5.1", "2.1", "32.1", "11.1", "32.5"]


def get_json(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def busy_count(rows):
    # A status shape we do not recognize is not evidence of an idle tuner.
    if not isinstance(rows, list) or not rows:
        raise ValueError("unknown_tuner_status")
    count = 0
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(
            r"tuner\d+", str(row.get("Resource", ""))
        ):
            raise ValueError("unknown_tuner_status")
        if any(
            row.get(key) not in (None, "", "none", 0)
            for key in row
            if key != "Resource"
        ):
            count += 1
    return count


def choose_channel(channels, history, now):
    """Oldest sampled station wins; local news/weather get bounded daypart bias."""
    hour = dt.datetime.fromtimestamp(now, TZ).hour
    news = hour in {5, 6, 7, 11, 12, 16, 17, 18, 21, 22}
    return min(
        channels,
        key=lambda row: (
            history.get(row["GuideNumber"], 0)
            - (
                180
                if news and row["GuideNumber"] in {"9.1", "7.1", "5.1", "2.1", "32.1"}
                else 0
            )
        ),
    )


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def capture(root, config, seconds=180):
    with lock(root, "capture"):
        clean_buffer(root)
        if not config.get("enabled"):
            status(root, "tv", "disabled")
            return None
        if config.get("scope") != "personal":
            raise ValueError("personal_scope_required")
        host = config.get("tuner_host", "")
        if not re.fullmatch(r"192\.168\.\d{1,3}\.\d{1,3}", host):
            raise ValueError("explicit_lan_tuner_required")
        base = "http://" + host
        rows = get_json(base + "/status.json")
        if len(rows) < 2 or busy_count(rows):
            status(root, "tv", "yielded", reason="another_tuner_consumer")
            return None
        if not capacity(root):
            status(root, "tv", "capacity_guard")
            return None
        allowed = config.get("channels", DEFAULT_CHANNELS)
        lineup = [
            r
            for r in get_json(base + "/lineup.json")
            if r.get("GuideNumber") in allowed and not r.get("DRM")
        ]
        if not lineup:
            raise ValueError("no_clear_configured_channels")
        history = read(root / "channel-history.json")
        chosen = choose_channel(lineup, history, time.time())
        channel = chosen["GuideNumber"]
        if not re.fullmatch(r"\d{1,3}\.\d{1,3}", channel):
            raise ValueError("invalid_channel")
        started = time.time()
        ident = "tv-" + str(int(started * 1000)) + "-" + channel.replace(".", "_")
        folder = root / "buffer" / ident
        folder.mkdir(parents=True)
        part = folder / "source.partial.ts"
        record = {
            "id": ident,
            "scope": "personal",
            "channel": channel,
            "station": str(chosen.get("GuideName", channel))[:80],
            "started": started,
            "complete": False,
            "selection": "unreviewed",
            "note": "Recorded window; story boundaries unverified",
        }
        write(folder / "capture.json", record)
        status(root, "tv", "capturing", channel=channel, capture_id=ident)
        seconds = max(15, min(300, seconds))
        # /auto allocates a free tuner or fails; never retune an occupied index.
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-rw_timeout",
            "5000000",
            "-i",
            f"http://{host}:5004/auto/v{channel}",
            "-t",
            str(seconds),
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            "mpegts",
            "-y",
            str(part),
        ]
        process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        reason = "window_complete"
        try:
            while process.poll() is None:
                time.sleep(2)
                if time.time() - started > seconds + 20:
                    reason = "capture_deadline"
                    break
                if busy_count(get_json(base + "/status.json")) > 1:
                    reason = "another_tuner_consumer"
                    break
                if not capacity(root):
                    reason = "capacity_guard"
                    break
        except (OSError, ValueError):
            reason = "tuner_status_unavailable"
        finally:
            stop(process)
        ended = time.time()
        record.update(
            ended=ended,
            complete=True,
            stop_reason=reason,
            capture_exit=process.returncode,
        )
        if part.exists() and part.stat().st_size > 18800:
            os.replace(part, folder / "source.ts")
            record["bytes"] = (folder / "source.ts").stat().st_size
            with (folder / "source.ts").open("rb") as saved:
                record["sha256"] = hashlib.file_digest(saved, "sha256").hexdigest()
        else:
            record["selection"] = "capture_failed"
            part.unlink(missing_ok=True)
        write(folder / "capture.json", record)
        history[channel] = ended
        write(root / "channel-history.json", history)
        status(
            root,
            "tv",
            "yielded" if reason != "window_complete" else "window_saved",
            channel=channel,
            capture_id=ident,
            reason=reason,
        )
        return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    try:
        capture(args.root, read(args.config), args.seconds)
    except (OSError, ValueError) as error:
        status(args.root, "tv", "error", reason=type(error).__name__)
        raise SystemExit(1)
