#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import mimetypes
import os
import socket
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

SESSION = os.environ.get("HOUSEBOT_CODEX_SESSION", "housebot-codex")
TMUX_SOCKET = os.environ.get("HOUSEBOT_CODEX_TMUX_SOCKET", SESSION).strip() or SESSION
HOST = os.environ.get("HOUSEBOT_CODEX_WEB_BIND", "127.0.0.1")
PORT = int(os.environ.get("HOUSEBOT_CODEX_WEB_PORT", "8787"))
TOKEN = os.environ.get("HOUSEBOT_CODEX_WEB_TOKEN", "").strip()
DEFAULT_UI_VERSION = "2026.03.25.5"
UI_VERSION = (
    os.environ.get("HOUSEBOT_CODEX_UI_VERSION", DEFAULT_UI_VERSION).strip()
    or DEFAULT_UI_VERSION
)
MAX_PANE_LINES = int(os.environ.get("HOUSEBOT_CODEX_WEB_PANE_LINES", "120"))
MAX_LOG_LINES = int(os.environ.get("HOUSEBOT_CODEX_WEB_LOG_LINES", "24"))
MAX_BLOCK_CHARS = int(os.environ.get("HOUSEBOT_CODEX_WEB_BLOCK_CHARS", "12000"))
MAX_HISTORY_ITEMS = int(os.environ.get("HOUSEBOT_CODEX_WEB_HISTORY_ITEMS", "24"))
STREAM_IDLE_SECONDS = float(
    os.environ.get("HOUSEBOT_CODEX_WEB_STREAM_IDLE_SECONDS", "4")
)
STREAM_PENDING_SECONDS = float(
    os.environ.get("HOUSEBOT_CODEX_WEB_STREAM_PENDING_SECONDS", "0.7")
)
DIRECTORY_VIEW_LIMIT = int(os.environ.get("HOUSEBOT_CODEX_DIRECTORY_VIEW_LIMIT", "200"))
FILE_PREVIEW_MAX_BYTES = int(
    os.environ.get("HOUSEBOT_CODEX_FILE_PREVIEW_MAX_BYTES", str(256 * 1024))
)
WORKDIR = os.environ.get("HOUSEBOT_CODEX_WORKDIR", "/opt/housebot")
CODEX_HOME = os.environ.get("HOUSEBOT_CODEX_HOME", "/root/.codex-housebot")
MODEL = os.environ.get("HOUSEBOT_CODEX_MODEL", "gpt-5.4")
REASONING_EFFORT = os.environ.get("HOUSEBOT_CODEX_REASONING_EFFORT", "xhigh")
AGENT_NAME = os.environ.get("HOUSEBOT_CODEX_AGENT_NAME", "Housebot")
CONSOLE_TITLE = os.environ.get("HOUSEBOT_CODEX_CONSOLE_TITLE", f"{AGENT_NAME} Console")
PROMPT_PLACEHOLDER = os.environ.get(
    "HOUSEBOT_CODEX_PROMPT_PLACEHOLDER",
    f"Ask {AGENT_NAME} to inspect a device, explain a problem, or make a targeted change.",
)
DEFAULT_UI_PROFILE = os.environ.get("HOUSEBOT_CODEX_UI_PROFILE", "dusk")
STATE_DIR = Path(
    os.environ.get("HOUSEBOT_CODEX_WEB_STATE_DIR", f"{CODEX_HOME}/web-bridge")
)
HOUSEBOT_SERVICE = os.environ.get("HOUSEBOT_SERVICE_NAME", "housebot")
PFSENSE_TIMER = os.environ.get(
    "HOUSEBOT_PFSENSE_TIMER_NAME", "housebot-pfsense-sync.timer"
)
CODEX_SERVICE = os.environ.get("HOUSEBOT_CODEX_SERVICE_NAME", "housebot-codex.service")
WEB_SERVICE = os.environ.get(
    "HOUSEBOT_CODEX_WEB_SERVICE_NAME", "housebot-codex-web.service"
)
TAILSCALE_SERVICE = os.environ.get("TAILSCALE_SERVICE_NAME", "tailscaled")

THREAD_ID_PATH = STATE_DIR / "thread_id.txt"
LAST_PROMPT_PATH = STATE_DIR / "last_prompt.txt"
LAST_RESPONSE_PATH = STATE_DIR / "last_response.txt"
LAST_ERROR_PATH = STATE_DIR / "last_error.txt"
STATUS_PATH = STATE_DIR / "status.json"
HISTORY_PATH = STATE_DIR / "history.jsonl"

PROMPT_LOCK = threading.Lock()
STATUS_LOCK = threading.Lock()
ACTIVE_PROMPT_THREAD: threading.Thread | None = None

PROFILE_MODE_ORDER = ("dark", "light")

UI_PROFILES: dict[str, dict[str, Any]] = {
    "dusk": {
        "label": "Dusk",
        "mode": "dark",
        "family": "dusk",
        "vars": {
            "bg": "#2a3240",
            "bg-soft": "#313a4a",
            "surface": "rgba(45, 54, 69, 0.88)",
            "surface-2": "#384355",
            "surface-3": "#445266",
            "border": "#4d5a70",
            "border-strong": "#65748d",
            "text": "#e4ebf2",
            "muted": "#a8b3c2",
            "accent": "#b8cedd",
            "accent-2": "#aac9be",
            "warn": "#d8c28d",
            "danger": "#d2aab6",
            "shadow": "0 14px 34px rgba(7, 10, 15, 0.12)",
            "radius": "20px",
            "glow-a": "rgba(184, 206, 221, 0.04)",
            "glow-b": "rgba(170, 201, 190, 0.03)",
            "body-start": "#29313e",
            "body-mid": "#303846",
            "body-end": "#353f4d",
        },
    },
    "dawn": {
        "label": "Dawn",
        "mode": "light",
        "family": "dusk",
        "vars": {
            "bg": "#f0e8dc",
            "bg-soft": "#f5efe6",
            "surface": "rgba(251, 247, 240, 0.88)",
            "surface-2": "#f2e7d7",
            "surface-3": "#eadbc7",
            "border": "#d5c6b3",
            "border-strong": "#c3b09a",
            "text": "#302821",
            "muted": "#766a5f",
            "accent": "#5d7386",
            "accent-2": "#698570",
            "warn": "#9a744d",
            "danger": "#9f6270",
            "shadow": "0 18px 40px rgba(88, 70, 48, 0.10)",
            "radius": "20px",
            "glow-a": "rgba(210, 188, 158, 0.18)",
            "glow-b": "rgba(198, 214, 196, 0.12)",
            "body-start": "#efe5d8",
            "body-mid": "#f5efe7",
            "body-end": "#ece4d7",
        },
    },
    "slate": {
        "label": "Slate",
        "mode": "dark",
        "family": "slate",
        "vars": {
            "bg": "#303642",
            "bg-soft": "#373e4b",
            "surface": "rgba(52, 59, 72, 0.88)",
            "surface-2": "#3f4755",
            "surface-3": "#4a5566",
            "border": "#556174",
            "border-strong": "#6e7e96",
            "text": "#e5ecf4",
            "muted": "#adb8c7",
            "accent": "#c1d0df",
            "accent-2": "#a7c0d1",
            "warn": "#d7c391",
            "danger": "#d0a7bb",
            "shadow": "0 14px 34px rgba(8, 10, 15, 0.12)",
            "radius": "20px",
            "glow-a": "rgba(193, 208, 223, 0.04)",
            "glow-b": "rgba(167, 192, 209, 0.03)",
            "body-start": "#2f3541",
            "body-mid": "#373e4a",
            "body-end": "#3d4552",
        },
    },
    "mist": {
        "label": "Mist",
        "mode": "light",
        "family": "slate",
        "vars": {
            "bg": "#edf2f5",
            "bg-soft": "#f5f8fa",
            "surface": "rgba(248, 251, 252, 0.88)",
            "surface-2": "#e9eff3",
            "surface-3": "#dde7ed",
            "border": "#c8d3db",
            "border-strong": "#b0c0cb",
            "text": "#25303a",
            "muted": "#6d7b88",
            "accent": "#496476",
            "accent-2": "#4d7b72",
            "warn": "#8e744d",
            "danger": "#94606f",
            "shadow": "0 18px 40px rgba(85, 103, 118, 0.10)",
            "radius": "20px",
            "glow-a": "rgba(194, 213, 226, 0.18)",
            "glow-b": "rgba(204, 218, 229, 0.14)",
            "body-start": "#e7eef2",
            "body-mid": "#f1f6f8",
            "body-end": "#e8eff3",
        },
    },
    "evergreen": {
        "label": "Evergreen",
        "mode": "dark",
        "family": "evergreen",
        "vars": {
            "bg": "#2a342c",
            "bg-soft": "#323d34",
            "surface": "rgba(47, 57, 49, 0.88)",
            "surface-2": "#3a453d",
            "surface-3": "#455347",
            "border": "#526358",
            "border-strong": "#697e70",
            "text": "#e2ede4",
            "muted": "#a8baaa",
            "accent": "#b8d1be",
            "accent-2": "#a7cec4",
            "warn": "#d5c58e",
            "danger": "#d0a8b2",
            "shadow": "0 14px 34px rgba(6, 10, 7, 0.12)",
            "radius": "20px",
            "glow-a": "rgba(184, 209, 190, 0.04)",
            "glow-b": "rgba(167, 206, 196, 0.03)",
            "body-start": "#2b342d",
            "body-mid": "#344036",
            "body-end": "#3a463c",
        },
    },
    "sage": {
        "label": "Sage",
        "mode": "light",
        "family": "evergreen",
        "vars": {
            "bg": "#edf1e8",
            "bg-soft": "#f4f7f1",
            "surface": "rgba(247, 250, 244, 0.9)",
            "surface-2": "#e8eee1",
            "surface-3": "#dce6d3",
            "border": "#c4d0bf",
            "border-strong": "#aebfa8",
            "text": "#263029",
            "muted": "#69756a",
            "accent": "#4f6f65",
            "accent-2": "#587b72",
            "warn": "#91744d",
            "danger": "#91616f",
            "shadow": "0 18px 40px rgba(73, 92, 72, 0.10)",
            "radius": "20px",
            "glow-a": "rgba(201, 217, 193, 0.18)",
            "glow-b": "rgba(200, 220, 213, 0.14)",
            "body-start": "#e8eee1",
            "body-mid": "#f2f6ee",
            "body-end": "#e6ece0",
        },
    },
}

RESPONSE_SPEED_TO_REASONING = {
    "fast": "low",
    "balanced": "medium",
    "careful": "xhigh",
}
RESPONSE_DETAIL_LABELS = {
    1: "Simple",
    2: "Lean",
    3: "Balanced",
    4: "Detailed",
    5: "Deep",
}
RESPONSE_DETAIL_INSTRUCTIONS = {
    1: "Use the minimum words needed. Prefer one short paragraph or a very short list. Skip background unless it is essential.",
    2: "Stay concise and practical. Keep explanation lean and avoid extra context unless it clearly helps.",
    3: "Use balanced depth. Cover the main answer, the key rationale, and the next useful detail.",
    4: "Go a layer deeper. Explain the reasoning, tradeoffs, and relevant context while staying organized.",
    5: "Be thorough. Include the important context, tradeoffs, and next steps, but stay concrete and readable.",
}


def reasoning_effort_to_speed(value: str | None) -> str:
    clean = str(value or "").strip().lower()
    if clean in {"low", "minimal"}:
        return "fast"
    if clean in {"medium", "med"}:
        return "balanced"
    return "careful"


def normalize_response_speed(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if clean in RESPONSE_SPEED_TO_REASONING:
        return clean
    return reasoning_effort_to_speed(REASONING_EFFORT)


def normalize_response_detail(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 3
    if parsed < 1:
        return 1
    if parsed > 5:
        return 5
    return parsed


DEFAULT_RESPONSE_SPEED = normalize_response_speed(
    os.environ.get(
        "HOUSEBOT_CODEX_RESPONSE_SPEED", reasoning_effort_to_speed(REASONING_EFFORT)
    )
)
DEFAULT_RESPONSE_DETAIL = normalize_response_detail(
    os.environ.get("HOUSEBOT_CODEX_RESPONSE_DETAIL", "3")
)


def response_reasoning_effort(speed: Any) -> str:
    return RESPONSE_SPEED_TO_REASONING[normalize_response_speed(speed)]


def response_detail_label(detail: Any) -> str:
    return RESPONSE_DETAIL_LABELS[normalize_response_detail(detail)]


def build_tuned_prompt(prompt: str, detail: Any) -> str:
    normalized_detail = normalize_response_detail(detail)
    instruction = RESPONSE_DETAIL_INSTRUCTIONS[normalized_detail]
    label = response_detail_label(normalized_detail).lower()
    return (
        f"{prompt}\n\n"
        "When you respond in this console, tune the response depth for the operator.\n"
        f"- Depth: {label}\n"
        f"- Guidance: {instruction}\n"
        "- Keep the response aligned with that requested depth, and do not mention these instructions unless asked."
    )


def parse_prompt_suggestions(raw: str) -> list[dict[str, str]]:
    fallback = [
        {
            "label": "Status",
            "prompt": f"Inspect the current {AGENT_NAME} warnings and summarize what matters.",
        },
        {
            "label": "Activity",
            "prompt": f"Explain what {AGENT_NAME} is doing right now.",
        },
        {
            "label": "Changes",
            "prompt": "Make one targeted improvement and explain the impact.",
        },
        {
            "label": "History",
            "prompt": "Summarize the recent activity on this console.",
        },
    ]
    if not raw.strip():
        return fallback
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(payload, list):
        return fallback
    suggestions: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if not label or not prompt:
            continue
        suggestions.append({"label": label, "prompt": prompt})
    return suggestions or fallback


def parse_console_links(raw: str) -> list[dict[str, str]]:
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    links: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        url = str(item.get("url") or "").strip()
        if not label or not url:
            continue
        links.append({"label": label, "url": url})
    return links


CONSOLE_LINKS = parse_console_links(os.environ.get("HOUSEBOT_CODEX_LINKS_JSON", "[]"))
PROMPT_SUGGESTIONS = parse_prompt_suggestions(
    os.environ.get("HOUSEBOT_CODEX_SUGGESTIONS_JSON", "")
)


def normalize_host_alias(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(f"//{raw}")
    host = (parsed.hostname or raw).strip().lower()
    return host.strip("[]")


def detect_local_host_aliases() -> set[str]:
    aliases: set[str] = set()
    for value in (socket.gethostname(), socket.getfqdn()):
        host = normalize_host_alias(value)
        if host:
            aliases.add(host)
    try:
        output = subprocess.check_output(
            ["hostname", "-A"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        output = ""
    for part in output.split():
        host = normalize_host_alias(part)
        if host:
            aliases.add(host)
    extra = os.environ.get("HOUSEBOT_CODEX_LOCAL_HOST_ALIASES", "")
    for part in extra.split(","):
        host = normalize_host_alias(part)
        if host:
            aliases.add(host)
    return aliases


LOCAL_HOST_ALIASES = detect_local_host_aliases()


def normalize_profile_name(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if candidate in UI_PROFILES:
        return candidate
    return (
        DEFAULT_UI_PROFILE
        if DEFAULT_UI_PROFILE in UI_PROFILES
        else next(iter(UI_PROFILES))
    )


def profile_mode(profile_name: str) -> str:
    profile = UI_PROFILES[normalize_profile_name(profile_name)]
    mode = str(profile.get("mode") or "dark").strip().lower()
    return mode if mode in PROFILE_MODE_ORDER else PROFILE_MODE_ORDER[0]


def profile_family(profile_name: str) -> str:
    profile = UI_PROFILES[normalize_profile_name(profile_name)]
    return str(profile.get("family") or normalize_profile_name(profile_name))


def profiles_for_mode(mode: str) -> list[tuple[str, dict[str, Any]]]:
    clean_mode = mode if mode in PROFILE_MODE_ORDER else PROFILE_MODE_ORDER[0]
    return [
        (slug, data)
        for slug, data in UI_PROFILES.items()
        if profile_mode(slug) == clean_mode
    ]


def profile_for_mode(profile_name: str, target_mode: str) -> str:
    target = target_mode if target_mode in PROFILE_MODE_ORDER else PROFILE_MODE_ORDER[0]
    normalized = normalize_profile_name(profile_name)
    if profile_mode(normalized) == target:
        return normalized
    family = profile_family(normalized)
    for slug in UI_PROFILES:
        if profile_mode(slug) == target and profile_family(slug) == family:
            return slug
    for slug in UI_PROFILES:
        if profile_mode(slug) == target:
            return slug
    return normalized


def profile_vars_css(profile_name: str) -> str:
    profile = UI_PROFILES[normalize_profile_name(profile_name)]
    return "\n".join(
        f"      --{key}: {value};" for key, value in profile["vars"].items()
    )


def build_console_href(*, token: str, profile: str) -> str:
    query: dict[str, str] = {}
    if token:
        query["token"] = token
    if profile:
        query["profile"] = profile
    if not query:
        return "/"
    return f"/?{urlencode(query)}"


def build_file_href(
    *,
    token: str,
    path: str,
    profile: str = "",
    raw: bool = False,
    download: bool = False,
) -> str:
    query: dict[str, str] = {"path": path}
    if token:
        query["token"] = token
    if profile:
        query["profile"] = profile
    if raw:
        query["raw"] = "1"
    if download:
        query["download"] = "1"
    return f"/api/file?{urlencode(query)}"


def render_console_link_url(
    raw_url: str, *, token: str, profile: str, request_host: str = ""
) -> str:
    rendered = (
        raw_url.replace("{token}", quote(token, safe=""))
        .replace("{profile}", quote(profile, safe=""))
        .strip()
    )
    current_host = normalize_host_alias(request_host)
    if not current_host:
        return rendered
    parsed = urlparse(rendered)
    target_host = normalize_host_alias(parsed.netloc or parsed.hostname or "")
    if not target_host or target_host not in LOCAL_HOST_ALIASES:
        return rendered
    port = f":{parsed.port}" if parsed.port else ""
    rewritten = parsed._replace(netloc=f"{current_host}{port}")
    return rewritten.geturl()


def now_ts() -> int:
    return int(time.time())


def run(
    cmd: list[str], *, input_text: str | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def tmux_cmd(*args: str) -> list[str]:
    return ["tmux", "-L", TMUX_SOCKET, *args]


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def truncate_block(text: str, limit: int = MAX_BLOCK_CHARS) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if len(value) <= limit:
        return value
    tail = value[-limit:]
    omitted = len(value) - len(tail)
    return f"[truncated {omitted} earlier characters]\n{tail}"


def summarize_text(text: str, limit: int = 180) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"


def resolve_file_target(raw: str) -> Path | None:
    candidate = (raw or "").strip()
    if not candidate:
        return None
    if candidate.startswith("file://"):
        candidate = urlparse(candidate).path
    if candidate.startswith("~/"):
        candidate = str(Path.home() / candidate[2:])
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = (Path(WORKDIR) / candidate).resolve()
    else:
        path = path.resolve()
    # The web viewer may only expose files in its configured workspace.
    # Resolve symlinks before checking containment.
    if not path.is_relative_to(Path(WORKDIR).resolve()):
        return None
    return path


def guess_file_content_type(path: Path) -> str:
    mime, _encoding = mimetypes.guess_type(path.name)
    if mime:
        if mime.startswith("text/"):
            return f"{mime}; charset=utf-8"
        return mime
    if path.suffix.lower() in {
        ".md",
        ".txt",
        ".py",
        ".sh",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".log",
        ".csv",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".sql",
    }:
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def human_size(size: int) -> str:
    value = float(size)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def is_text_preview_type(path: Path, content_type: str) -> bool:
    if content_type.startswith("text/"):
        return True
    return path.suffix.lower() in {
        ".md",
        ".txt",
        ".py",
        ".sh",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".log",
        ".csv",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".sql",
    }


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return default


def write_text(path: Path, value: str) -> None:
    ensure_state_dir()
    path.write_text(value, encoding="utf-8")


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(default)
    except json.JSONDecodeError:
        return dict(default)
    if not isinstance(payload, dict):
        return dict(default)
    merged = dict(default)
    merged.update(payload)
    return merged


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_state_dir()
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def load_history(limit: int = MAX_HISTORY_ITEMS) -> list[dict[str, Any]]:
    ensure_state_dir()
    entries: list[dict[str, Any]] = []
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return entries
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    if limit and len(entries) > limit:
        return entries[-limit:]
    return entries


def append_history_entry(
    *,
    prompt: str,
    response: str,
    error_text: str,
    started_at: int,
    finished_at: int,
    thread_id: str,
    speed: str,
    detail: int,
) -> None:
    entries = load_history(limit=0)
    entries.append(
        {
            "detail": normalize_response_detail(detail),
            "error": error_text,
            "finished_at": finished_at,
            "prompt": prompt,
            "response": response,
            "speed": normalize_response_speed(speed),
            "started_at": started_at,
            "thread_id": thread_id,
        }
    )
    trimmed = entries[-MAX_HISTORY_ITEMS:]
    ensure_state_dir()
    payload = "\n".join(json.dumps(item, sort_keys=True) for item in trimmed)
    if payload:
        payload += "\n"
    HISTORY_PATH.write_text(payload, encoding="utf-8")


def default_status_meta() -> dict[str, Any]:
    return {
        "pending": False,
        "state": "idle",
        "status_message": "Ready.",
        "running_prompt": "",
        "running_speed": DEFAULT_RESPONSE_SPEED,
        "running_detail": DEFAULT_RESPONSE_DETAIL,
        "last_speed": DEFAULT_RESPONSE_SPEED,
        "last_detail": DEFAULT_RESPONSE_DETAIL,
        "last_started_at": 0,
        "last_finished_at": 0,
        "last_action": "",
        "last_action_at": 0,
        "last_action_detail": "",
        "updated_at": 0,
        "queued_prompts": [],
    }


def load_status_meta() -> dict[str, Any]:
    ensure_state_dir()
    return read_json(STATUS_PATH, default_status_meta())


def normalize_queue(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return items
    for entry in value:
        if isinstance(entry, str):
            prompt = entry.strip()
            queued_at = 0
            speed = DEFAULT_RESPONSE_SPEED
            detail = DEFAULT_RESPONSE_DETAIL
        elif isinstance(entry, dict):
            prompt = str(entry.get("prompt") or "").strip()
            try:
                queued_at = int(entry.get("queued_at") or 0)
            except (TypeError, ValueError):
                queued_at = 0
            speed = normalize_response_speed(entry.get("speed"))
            detail = normalize_response_detail(entry.get("detail"))
        else:
            continue
        if prompt:
            items.append(
                {
                    "prompt": prompt,
                    "queued_at": queued_at,
                    "speed": speed,
                    "detail": detail,
                }
            )
    return items


def save_status_meta(meta: dict[str, Any]) -> dict[str, Any]:
    payload = dict(default_status_meta())
    payload.update(meta)
    payload["running_speed"] = normalize_response_speed(payload.get("running_speed"))
    payload["running_detail"] = normalize_response_detail(payload.get("running_detail"))
    payload["last_speed"] = normalize_response_speed(payload.get("last_speed"))
    payload["last_detail"] = normalize_response_detail(payload.get("last_detail"))
    payload["queued_prompts"] = normalize_queue(payload.get("queued_prompts"))
    payload["updated_at"] = now_ts()
    write_json(STATUS_PATH, payload)
    return payload


def update_status_meta(**updates: Any) -> dict[str, Any]:
    with STATUS_LOCK:
        meta = load_status_meta()
        meta.update(updates)
        return save_status_meta(meta)


def prompt_thread_alive() -> bool:
    return ACTIVE_PROMPT_THREAD is not None and ACTIVE_PROMPT_THREAD.is_alive()


def launch_prompt_worker(prompt: str, started_at: int, speed: str, detail: int) -> None:
    global ACTIVE_PROMPT_THREAD
    thread = threading.Thread(
        target=_prompt_worker,
        args=(
            prompt,
            started_at,
            normalize_response_speed(speed),
            normalize_response_detail(detail),
        ),
        daemon=True,
    )
    ACTIVE_PROMPT_THREAD = thread
    thread.start()


def queue_prompt(prompt: str, speed: str, detail: int) -> dict[str, Any]:
    with STATUS_LOCK:
        meta = load_status_meta()
        queue = normalize_queue(meta.get("queued_prompts"))
        queue.append(
            {
                "prompt": prompt,
                "queued_at": now_ts(),
                "speed": normalize_response_speed(speed),
                "detail": normalize_response_detail(detail),
            }
        )
        meta["queued_prompts"] = queue
        save_status_meta(meta)
    return current_snapshot()


def recover_stale_prompt_state() -> None:
    if prompt_thread_alive():
        return
    should_launch = False
    with STATUS_LOCK:
        meta = load_status_meta()
        queue = normalize_queue(meta.get("queued_prompts"))
        running_prompt = str(meta.get("running_prompt") or "").strip()
        if meta.get("pending") and running_prompt:
            queue.insert(
                0,
                {
                    "prompt": running_prompt,
                    "queued_at": int(meta.get("last_started_at") or now_ts()),
                    "speed": normalize_response_speed(meta.get("running_speed")),
                    "detail": normalize_response_detail(meta.get("running_detail")),
                },
            )
        if not meta.get("pending") and not queue:
            return
        meta.update(
            {
                "pending": False,
                "state": "idle",
                "status_message": (
                    "Ready." if not queue else "Recovering queued prompt…"
                ),
                "running_prompt": "",
                "queued_prompts": queue,
            }
        )
        save_status_meta(meta)
        should_launch = bool(queue)
    if should_launch:
        next_prompt = start_next_queued_prompt()
        if next_prompt:
            queued_prompt, queued_started_at, queued_speed, queued_detail = next_prompt
            launch_prompt_worker(
                queued_prompt, queued_started_at, queued_speed, queued_detail
            )


def start_next_queued_prompt() -> tuple[str, int, str, int] | None:
    with STATUS_LOCK:
        meta = load_status_meta()
        queue = normalize_queue(meta.get("queued_prompts"))
        if not queue:
            meta["queued_prompts"] = []
            save_status_meta(meta)
            return None
        item = queue.pop(0)
        started_at = now_ts()
        prompt = item["prompt"]
        speed = normalize_response_speed(item.get("speed"))
        detail = normalize_response_detail(item.get("detail"))
        write_text(LAST_PROMPT_PATH, prompt)
        write_text(LAST_RESPONSE_PATH, "[waiting for reply]")
        write_text(LAST_ERROR_PATH, "")
        meta.update(
            {
                "pending": True,
                "state": "running",
                "status_message": f"{AGENT_NAME} is working on your prompt.",
                "running_prompt": prompt,
                "running_speed": speed,
                "running_detail": detail,
                "last_started_at": started_at,
                "queued_prompts": queue,
            }
        )
        save_status_meta(meta)
    return prompt, started_at, speed, detail


def record_action(action: str, detail: str) -> None:
    update_status_meta(
        last_action=action,
        last_action_at=now_ts(),
        last_action_detail=detail,
        status_message=detail,
    )


def session_exists() -> bool:
    proc = run(tmux_cmd("has-session", "-t", SESSION))
    return proc.returncode == 0


def ensure_session() -> bool:
    if session_exists():
        return True
    run(["systemctl", "start", CODEX_SERVICE])
    for _ in range(20):
        if session_exists():
            return True
        time.sleep(0.5)
    return False


def capture_pane() -> str:
    if not session_exists():
        return "[session unavailable]"
    proc = run(
        tmux_cmd(
            "capture-pane",
            "-p",
            "-t",
            f"{SESSION}:0.0",
            "-S",
            f"-{MAX_PANE_LINES}",
        )
    )
    text = proc.stdout or proc.stderr
    return truncate_block(text) or "[pane empty]"


def send_text(text: str) -> None:
    if not ensure_session():
        raise RuntimeError("Codex session could not be started.")
    buffer_name = f"{SESSION}-web-{int(time.time() * 1000)}"
    try:
        run(
            tmux_cmd("load-buffer", "-b", buffer_name, "-"), input_text=text, check=True
        )
        run(
            tmux_cmd("paste-buffer", "-d", "-b", buffer_name, "-t", f"{SESSION}:0.0"),
            check=True,
        )
        run(tmux_cmd("send-keys", "-t", f"{SESSION}:0.0", "Enter"), check=True)
    finally:
        run(tmux_cmd("delete-buffer", "-b", buffer_name))
    record_action("tmux-send", f"Sent raw text to tmux: {summarize_text(text, 140)}")


def send_interrupt() -> None:
    if ensure_session():
        run(tmux_cmd("send-keys", "-t", f"{SESSION}:0.0", "C-c"), check=True)
    record_action("tmux-interrupt", "Sent Ctrl+C to the interactive tmux session.")


def restart_session() -> None:
    run(tmux_cmd("kill-session", "-t", SESSION))
    run(["systemctl", "restart", CODEX_SERVICE])
    ensure_session()
    record_action(
        "tmux-restart", f"Restarted the interactive {AGENT_NAME} Codex tmux session."
    )


def service_status(units: list[str]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for unit in units:
        clean = unit.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        proc = run(["systemctl", "is-active", clean])
        value = (proc.stdout or proc.stderr).strip() or "unknown"
        results.append((clean, value))
    return results


def housebot_log_tail() -> str:
    proc = run(
        [
            "journalctl",
            "-u",
            HOUSEBOT_SERVICE,
            "-n",
            str(MAX_LOG_LINES),
            "--no-pager",
            "-o",
            "cat",
        ]
    )
    text = proc.stdout or proc.stderr
    return truncate_block(text) or "[no housebot journal output]"


def _execute_codex_prompt(prompt: str, speed: str, detail: int) -> tuple[str, str, str]:
    session_id = read_text(THREAD_ID_PATH)
    output_path = STATE_DIR / "last_message.txt"
    if output_path.exists():
        output_path.unlink()

    normalized_speed = normalize_response_speed(speed)
    normalized_detail = normalize_response_detail(detail)
    cmd = [
        "codex",
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "-m",
        MODEL,
        "-c",
        f'model_reasoning_effort="{response_reasoning_effort(normalized_speed)}"',
        "-C",
        WORKDIR,
        "-o",
        str(output_path),
    ]
    tuned_prompt = build_tuned_prompt(prompt, normalized_detail)
    if session_id:
        cmd.extend(["resume", session_id, tuned_prompt])
    else:
        cmd.append(tuned_prompt)

    env = dict(os.environ)
    env["CODEX_HOME"] = CODEX_HOME
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)

    new_session_id = session_id
    messages: list[str] = []
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            candidate = str(event.get("thread_id") or "").strip()
            if candidate:
                new_session_id = candidate
        elif event.get("type") == "turn.failed":
            err = event.get("error") or {}
            msg = str(err.get("message") or "").strip()
            if msg:
                messages.append(msg)

    if new_session_id:
        write_text(THREAD_ID_PATH, new_session_id)

    response = read_text(output_path)
    error_text = "\n".join(
        part for part in [proc.stderr.strip(), "\n".join(messages).strip()] if part
    ).strip()
    return response, error_text, new_session_id


def _prompt_worker(prompt: str, started_at: int, speed: str, detail: int) -> None:
    global ACTIVE_PROMPT_THREAD
    next_prompt: tuple[str, int, str, int] | None = None
    try:
        with PROMPT_LOCK:
            normalized_speed = normalize_response_speed(speed)
            normalized_detail = normalize_response_detail(detail)
            response, error_text, thread_id = _execute_codex_prompt(
                prompt, normalized_speed, normalized_detail
            )
            if not response and not error_text:
                error_text = "No final response was returned."
            finished_at = now_ts()
            write_text(LAST_PROMPT_PATH, prompt)
            write_text(LAST_RESPONSE_PATH, response or "[no response returned]")
            write_text(LAST_ERROR_PATH, error_text)
            append_history_entry(
                prompt=prompt,
                response=response or "[no response returned]",
                error_text=error_text,
                started_at=started_at,
                finished_at=finished_at,
                thread_id=thread_id,
                speed=normalized_speed,
                detail=normalized_detail,
            )
            update_status_meta(
                pending=False,
                state="ok" if response else "error",
                status_message=(
                    "Web prompt completed." if response else "Web prompt failed."
                ),
                running_prompt="",
                running_speed=normalized_speed,
                running_detail=normalized_detail,
                last_speed=normalized_speed,
                last_detail=normalized_detail,
                last_finished_at=finished_at,
            )
            next_prompt = start_next_queued_prompt()
    except Exception as exc:  # pragma: no cover - defensive bridge hardening
        finished_at = now_ts()
        write_text(LAST_PROMPT_PATH, prompt)
        write_text(LAST_RESPONSE_PATH, "")
        write_text(LAST_ERROR_PATH, str(exc))
        append_history_entry(
            prompt=prompt,
            response="",
            error_text=str(exc),
            started_at=started_at,
            finished_at=finished_at,
            thread_id=read_text(THREAD_ID_PATH),
            speed=speed,
            detail=detail,
        )
        update_status_meta(
            pending=False,
            state="error",
            status_message="Web prompt crashed.",
            running_prompt="",
            running_speed=normalize_response_speed(speed),
            running_detail=normalize_response_detail(detail),
            last_speed=normalize_response_speed(speed),
            last_detail=normalize_response_detail(detail),
            last_finished_at=finished_at,
        )
        next_prompt = start_next_queued_prompt()
    ACTIVE_PROMPT_THREAD = None
    if next_prompt:
        queued_prompt, queued_started_at, queued_speed, queued_detail = next_prompt
        launch_prompt_worker(
            queued_prompt, queued_started_at, queued_speed, queued_detail
        )


def start_web_prompt(
    prompt: str, speed: str, detail: int
) -> tuple[bool, dict[str, Any]]:
    clean = prompt.strip()
    if not clean:
        return False, current_snapshot()
    normalized_speed = normalize_response_speed(speed)
    normalized_detail = normalize_response_detail(detail)
    recover_stale_prompt_state()
    with STATUS_LOCK:
        meta = load_status_meta()
        if meta.get("pending"):
            pass
        else:
            write_text(LAST_PROMPT_PATH, clean)
            write_text(LAST_RESPONSE_PATH, "[waiting for reply]")
            write_text(LAST_ERROR_PATH, "")
            meta.update(
                {
                    "pending": True,
                    "state": "running",
                    "status_message": f"{AGENT_NAME} is working on your prompt.",
                    "running_prompt": clean,
                    "running_speed": normalized_speed,
                    "running_detail": normalized_detail,
                    "last_started_at": now_ts(),
                }
            )
            save_status_meta(meta)
            started_at = int(meta.get("last_started_at") or now_ts())
            launch_prompt_worker(clean, started_at, normalized_speed, normalized_detail)
            return True, current_snapshot()
    return True, queue_prompt(clean, normalized_speed, normalized_detail)


def current_snapshot() -> dict[str, Any]:
    recover_stale_prompt_state()
    meta = load_status_meta()
    history = load_history()
    queued_prompts = normalize_queue(meta.get("queued_prompts"))
    services = [
        {"name": name, "state": state}
        for name, state in service_status(
            [
                HOUSEBOT_SERVICE,
                PFSENSE_TIMER,
                CODEX_SERVICE,
                WEB_SERVICE,
                TAILSCALE_SERVICE,
            ]
        )
    ]
    snapshot_at = now_ts()
    return {
        "pending": bool(meta.get("pending")),
        "state": str(meta.get("state") or "idle"),
        "status_message": str(meta.get("status_message") or "Ready."),
        "running_prompt": str(meta.get("running_prompt") or ""),
        "running_speed": normalize_response_speed(meta.get("running_speed")),
        "running_detail": normalize_response_detail(meta.get("running_detail")),
        "last_speed": normalize_response_speed(meta.get("last_speed")),
        "last_detail": normalize_response_detail(meta.get("last_detail")),
        "last_started_at": int(meta.get("last_started_at") or 0),
        "last_finished_at": int(meta.get("last_finished_at") or 0),
        "updated_at": snapshot_at,
        "state_updated_at": int(meta.get("updated_at") or 0),
        "last_action": str(meta.get("last_action") or ""),
        "last_action_at": int(meta.get("last_action_at") or 0),
        "last_action_detail": str(meta.get("last_action_detail") or ""),
        "thread_id": read_text(THREAD_ID_PATH),
        "last_prompt": read_text(LAST_PROMPT_PATH, "[no prompt yet]"),
        "last_response": read_text(LAST_RESPONSE_PATH, "[no response yet]"),
        "last_error": read_text(LAST_ERROR_PATH),
        "history": history,
        "queued_prompts": queued_prompts,
        "queue_depth": len(queued_prompts),
        "permissions_mode": "danger-full-access",
        "chat_model": MODEL,
        "chat_reasoning_effort": response_reasoning_effort(DEFAULT_RESPONSE_SPEED),
        "default_speed": DEFAULT_RESPONSE_SPEED,
        "default_detail": DEFAULT_RESPONSE_DETAIL,
        "tmux_session": SESSION,
        "services": services,
        "pane": capture_pane(),
        "logs": housebot_log_tail(),
    }


def snapshot_marker(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("pending"),
        snapshot.get("state"),
        snapshot.get("state_updated_at"),
        snapshot.get("last_action_at"),
        snapshot.get("thread_id"),
        snapshot.get("last_prompt"),
        snapshot.get("last_response"),
        snapshot.get("last_error"),
        len(snapshot.get("history") or []),
        snapshot.get("queue_depth"),
        snapshot.get("running_speed"),
        snapshot.get("running_detail"),
        snapshot.get("last_speed"),
        snapshot.get("last_detail"),
    )


def token_ok(params: dict[str, list[str]]) -> bool:
    if not TOKEN:
        return True
    values = params.get("token", [])
    return any(value == TOKEN for value in values)


def script_json(value: Any) -> str:
    return json.dumps(value).replace("</", "<\\/")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        api_path = parsed.path.startswith("/api/")

        if not token_ok(params):
            if parsed.path == "/":
                self.render_token_gate(params)
                return
            if api_path:
                self.json_response(
                    {"error": "missing or invalid token"}, status=HTTPStatus.FORBIDDEN
                )
                return
            self.send_error(HTTPStatus.FORBIDDEN, "missing or invalid token")
            return

        if parsed.path == "/healthz":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return

        if parsed.path == "/api/status":
            self.json_response(current_snapshot())
            return

        if parsed.path == "/api/stream":
            self.stream_status()
            return

        if parsed.path == "/api/file":
            self.serve_file_target(params)
            return

        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.render_index(params)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        api_path = parsed.path.startswith("/api/")
        params = self._read_post_params()

        if not token_ok(params):
            if api_path:
                self.json_response(
                    {"error": "missing or invalid token"}, status=HTTPStatus.FORBIDDEN
                )
                return
            self.send_error(HTTPStatus.FORBIDDEN, "missing or invalid token")
            return

        if parsed.path in {"/ask", "/api/ask"}:
            message = (params.get("message", [""])[0]).strip()
            speed = normalize_response_speed((params.get("speed") or [""])[0])
            detail = normalize_response_detail((params.get("detail") or [""])[0])
            if not message:
                if api_path:
                    self.json_response(
                        {
                            "error": "message is required",
                            "snapshot": current_snapshot(),
                        },
                        status=HTTPStatus.BAD_REQUEST,
                    )
                else:
                    self.redirect_root(params)
                return
            accepted, snapshot = start_web_prompt(message, speed, detail)
            if api_path:
                self.json_response(
                    {
                        "accepted": accepted,
                        "error": "" if accepted else "a web prompt is already running",
                        "snapshot": snapshot,
                    },
                    status=HTTPStatus.ACCEPTED if accepted else HTTPStatus.CONFLICT,
                )
            else:
                self.redirect_root(params)
            return

        if parsed.path in {"/send", "/api/send"}:
            message = (params.get("message", [""])[0]).strip()
            if message:
                send_text(message)
            snapshot = current_snapshot()
            if api_path:
                self.json_response(
                    {"ok": True, "snapshot": snapshot}, status=HTTPStatus.ACCEPTED
                )
            else:
                self.redirect_root(params)
            return

        if parsed.path in {"/interrupt", "/api/interrupt"}:
            send_interrupt()
            snapshot = current_snapshot()
            if api_path:
                self.json_response(
                    {"ok": True, "snapshot": snapshot}, status=HTTPStatus.ACCEPTED
                )
            else:
                self.redirect_root(params)
            return

        if parsed.path in {"/restart", "/api/restart"}:
            restart_session()
            snapshot = current_snapshot()
            if api_path:
                self.json_response(
                    {"ok": True, "snapshot": snapshot}, status=HTTPStatus.ACCEPTED
                )
            else:
                self.redirect_root(params)
            return

        if api_path:
            self.json_response({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _read_post_params(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return parse_qs(raw)

    def json_response(
        self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def render_directory_view(self, path: Path, params: dict[str, list[str]]) -> None:
        profile = normalize_profile_name((params.get("profile") or [""])[0])
        entries = sorted(
            path.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )[:DIRECTORY_VIEW_LIMIT]
        entry_items = "".join(
            (
                f'<li><a href="{html.escape(build_file_href(token=TOKEN, path=str(entry.resolve()), profile=profile))}">'
                f'{html.escape(entry.name)}{"/" if entry.is_dir() else ""}</a></li>'
            )
            for entry in entries
        )
        back_href = build_console_href(token=TOKEN, profile=profile)
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{html.escape(path.name or str(path))}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      background: #2f3541;
      color: #e5ecf4;
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", Helvetica, sans-serif;
      padding: 20px;
      box-sizing: border-box;
    }}
    main {{
      max-width: 900px;
      margin: 0 auto;
      background: rgba(52, 59, 72, 0.9);
      border: 1px solid #556174;
      border-radius: 20px;
      padding: 18px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 1.25rem;
    }}
    p, li {{
      line-height: 1.5;
    }}
    code {{
      display: block;
      padding: 10px 12px;
      border-radius: 14px;
      background: #373e4b;
      border: 1px solid #556174;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    a {{
      color: #c1d0df;
    }}
    ul {{
      margin: 14px 0 0;
      padding-left: 18px;
    }}
  </style>
</head>
<body>
    <main>
    <h1>{html.escape(path.name or str(path))}</h1>
    <p>{len(entries)} entries shown.</p>
    <code>{html.escape(str(path))}</code>
    <p><a href="{html.escape(back_href)}">Back to console</a></p>
    <ul>{entry_items or "<li>[empty]</li>"}</ul>
  </main>
</body>
</html>
"""
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def render_file_view(
        self,
        path: Path,
        content_type: str,
        stat: os.stat_result,
        params: dict[str, list[str]],
    ) -> None:
        profile = normalize_profile_name((params.get("profile") or [""])[0])
        back_href = build_console_href(token=TOKEN, profile=profile)
        raw_href = build_file_href(
            token=TOKEN, path=str(path), profile=profile, raw=True
        )
        download_href = build_file_href(
            token=TOKEN, path=str(path), profile=profile, download=True
        )
        preview_text = ""
        preview_note = ""
        preview_available = is_text_preview_type(path, content_type)
        if preview_available:
            with path.open("rb") as handle:
                data = handle.read(FILE_PREVIEW_MAX_BYTES + 1)
            preview_available = True
            if len(data) > FILE_PREVIEW_MAX_BYTES:
                preview_note = (
                    f"Preview truncated at {human_size(FILE_PREVIEW_MAX_BYTES)}."
                )
                data = data[:FILE_PREVIEW_MAX_BYTES]
            preview_text = data.decode("utf-8", errors="replace")
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{html.escape(path.name)}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      background: #2f3541;
      color: #e5ecf4;
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", Helvetica, sans-serif;
      padding: 20px;
      box-sizing: border-box;
    }}
    main {{
      max-width: 980px;
      margin: 0 auto;
      background: rgba(52, 59, 72, 0.9);
      border: 1px solid #556174;
      border-radius: 20px;
      padding: 18px;
      display: grid;
      gap: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: 1.25rem;
    }}
    p {{
      margin: 0;
      line-height: 1.5;
      color: #adb8c7;
    }}
    code, pre {{
      margin: 0;
      padding: 12px;
      border-radius: 14px;
      background: #373e4b;
      border: 1px solid #556174;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 9px;
      border-radius: 999px;
      border: 1px solid #556174;
      background: #3f4755;
      color: #e5ecf4;
      text-decoration: none;
      font-size: 0.78rem;
    }}
    a {{
      color: #c1d0df;
    }}
  </style>
</head>
<body>
  <main>
    <div class="row">
      <a class="chip" href="{html.escape(back_href)}">Back to console</a>
      <a class="chip" href="{html.escape(raw_href)}">Raw</a>
      <a class="chip" href="{html.escape(download_href)}">Download</a>
    </div>
    <h1>{html.escape(path.name)}</h1>
    <p>{html.escape(str(path))}</p>
    <div class="row">
      <span class="chip">{html.escape(content_type)}</span>
      <span class="chip">{html.escape(human_size(stat.st_size))}</span>
    </div>
    {"<p>" + html.escape(preview_note) + "</p>" if preview_note else ""}
    {f"<pre>{html.escape(preview_text)}</pre>" if preview_available else "<p>Preview is not available for this file type. Use Raw or Download.</p>"}
  </main>
</body>
</html>
"""
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_file_bytes(
        self, path: Path, content_type: str, stat: os.stat_result, *, download: bool
    ) -> None:
        disposition = "attachment" if download else "inline"
        if "\r" in content_type or "\n" in content_type:
            content_type = "application/octet-stream"
        with path.open("rb") as handle:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(stat.st_size))
            self.send_header(
                "Content-Disposition",
                f"{disposition}; filename*=UTF-8''{quote(path.name, safe='')}",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def serve_file_target(self, params: dict[str, list[str]]) -> None:
        raw_path = (params.get("path") or [""])[0]
        target = resolve_file_target(raw_path)
        if target is None:
            self.send_error(HTTPStatus.BAD_REQUEST, "missing path")
            return
        if not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "file not found")
            return
        if target.is_dir():
            self.render_directory_view(target, params)
            return
        try:
            stat = target.stat()
        except PermissionError:
            self.send_error(HTTPStatus.FORBIDDEN, "file is not readable")
            return
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "file not found")
            return
        content_type = guess_file_content_type(target)
        wants_raw = (params.get("raw") or [""])[0] == "1"
        wants_download = (params.get("download") or [""])[0] == "1"
        if wants_raw or wants_download:
            self.send_file_bytes(target, content_type, stat, download=wants_download)
            return
        self.render_file_view(target, content_type, stat, params)

    def stream_status(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last_marker: tuple[Any, ...] | None = None
        last_sent = 0.0
        try:
            while True:
                snapshot = current_snapshot()
                marker = snapshot_marker(snapshot)
                now = time.time()
                if marker != last_marker:
                    payload = json.dumps(snapshot).encode("utf-8")
                    self.wfile.write(b"event: snapshot\n")
                    self.wfile.write(b"data: ")
                    self.wfile.write(payload)
                    self.wfile.write(b"\n\n")
                    self.wfile.flush()
                    last_marker = marker
                    last_sent = now
                elif (now - last_sent) >= STREAM_IDLE_SECONDS:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_sent = now
                time.sleep(
                    STREAM_PENDING_SECONDS
                    if snapshot.get("pending")
                    else STREAM_IDLE_SECONDS
                )
        except (BrokenPipeError, ConnectionResetError):
            return

    def redirect_root(self, params: dict[str, list[str]]) -> None:
        token_value = TOKEN or ((params.get("token") or [""])[0])
        profile_value = normalize_profile_name((params.get("profile") or [""])[0])
        target = build_console_href(token=token_value, profile=profile_value)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", target)
        self.end_headers()

    def render_index(self, params: dict[str, list[str]]) -> None:
        ensure_session()
        active_profile = normalize_profile_name((params.get("profile") or [""])[0])
        active_profile_label = UI_PROFILES[active_profile]["label"]
        active_mode = profile_mode(active_profile)
        opposite_mode = "light" if active_mode == "dark" else "dark"
        token_value_raw = TOKEN or ((params.get("token") or [""])[0])
        request_host = self.headers.get("Host", "")
        theme_toggle_target = profile_for_mode(active_profile, opposite_mode)
        theme_toggle_label = opposite_mode.title()
        settings_mode_links_html = "".join(
            f'<a class="profile-chip setting-pill{" active" if mode == active_mode else ""}" href="{html.escape(build_console_href(token=token_value_raw, profile=profile_for_mode(active_profile, mode)))}">{html.escape(mode.title())}</a>'
            for mode in PROFILE_MODE_ORDER
        )
        settings_profile_links_html = "".join(
            f'<a class="profile-chip setting-pill{" active" if slug == active_profile else ""}" href="{html.escape(build_console_href(token=token_value_raw, profile=slug))}">{html.escape(data["label"])}</a>'
            for slug, data in profiles_for_mode(active_mode)
        )
        console_links_html = "".join(
            f'<a class="quick-link" href="{html.escape(render_console_link_url(link["url"], token=token_value_raw, profile=active_profile, request_host=request_host))}" target="_blank" rel="noreferrer">{html.escape(link["label"])}</a>'
            for link in CONSOLE_LINKS
        )
        console_nav_html = (
            f'<nav class="console-nav" aria-label="Console links"><span class="console-nav-label">Consoles</span>{console_links_html}</nav>'
            if console_links_html
            else ""
        )
        prompt_suggestions_html = "".join(
            f'<button type="button" class="ghost suggestion-chip" data-suggestion="{html.escape(item["prompt"], quote=True)}">{html.escape(item["label"])}</button>'
            for item in PROMPT_SUGGESTIONS
        )
        browse_links: list[str] = []
        if Path(WORKDIR).exists():
            browse_links.append(
                f'<a class="quick-link" href="{html.escape(build_file_href(token=token_value_raw, path=WORKDIR, profile=active_profile))}" target="_blank" rel="noreferrer">Workspace</a>'
            )
        if STATE_DIR.exists():
            browse_links.append(
                f'<a class="quick-link" href="{html.escape(build_file_href(token=token_value_raw, path=str(STATE_DIR), profile=active_profile))}" target="_blank" rel="noreferrer">Bridge State</a>'
            )
        settings_browse_links_html = "".join(browse_links)
        token_suffix = f"?token={html.escape(TOKEN)}" if TOKEN else ""
        initial_snapshot = script_json(
            {
                "pending": False,
                "state": "idle",
                "status_message": "Loading current status…",
                "running_prompt": "",
                "running_speed": DEFAULT_RESPONSE_SPEED,
                "running_detail": DEFAULT_RESPONSE_DETAIL,
                "last_speed": DEFAULT_RESPONSE_SPEED,
                "last_detail": DEFAULT_RESPONSE_DETAIL,
                "last_started_at": 0,
                "last_finished_at": 0,
                "updated_at": 0,
                "state_updated_at": 0,
                "last_action": "",
                "last_action_at": 0,
                "last_action_detail": "",
                "thread_id": "",
                "last_prompt": "[no prompt yet]",
                "last_response": "[no response yet]",
                "last_error": "",
                "history": [],
                "queued_prompts": [],
                "queue_depth": 0,
                "permissions_mode": "danger-full-access",
                "chat_model": MODEL,
                "chat_reasoning_effort": response_reasoning_effort(
                    DEFAULT_RESPONSE_SPEED
                ),
                "default_speed": DEFAULT_RESPONSE_SPEED,
                "default_detail": DEFAULT_RESPONSE_DETAIL,
                "tmux_session": SESSION,
                "services": [],
                "pane": "",
                "logs": "",
            }
        )
        token_value = script_json(TOKEN)
        active_profile_name_json = script_json(active_profile)
        active_profile_label_json = script_json(active_profile_label)
        default_response_speed_json = script_json(DEFAULT_RESPONSE_SPEED)
        default_response_detail_json = script_json(DEFAULT_RESPONSE_DETAIL)
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{html.escape(CONSOLE_TITLE)}</title>
  <style>
    :root {{
{profile_vars_css(active_profile)}
    }}
    * {{
      box-sizing: border-box;
    }}
    html,
    body {{
      min-height: 100%;
    }}
    body {{
      margin: 0;
      min-height: 100dvh;
      background:
        radial-gradient(circle at top left, var(--glow-a), transparent 26%),
        radial-gradient(circle at bottom right, var(--glow-b), transparent 22%),
        linear-gradient(180deg, var(--body-start) 0%, var(--body-mid) 48%, var(--body-end) 100%);
      color: var(--text);
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", Helvetica, sans-serif;
      overscroll-behavior-y: auto;
    }}
    body.system-open,
    body.settings-open {{
      overflow: hidden;
    }}
    ::selection {{
      background: rgba(125, 211, 252, 0.26);
      color: #f8fbff;
    }}
    a {{
      color: var(--accent);
    }}
    button,
    a,
    textarea {{
      touch-action: manipulation;
      -webkit-tap-highlight-color: rgba(178, 92, 52, 0.12);
    }}
    .app-shell {{
      max-width: 1240px;
      margin: 0 auto;
      min-height: 100dvh;
      padding: 8px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .surface {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: 0 10px 24px rgba(12, 16, 22, 0.07);
      backdrop-filter: blur(10px);
    }}
    .brand {{
      min-width: 0;
    }}
    .brand h1 {{
      margin: 0;
      font-size: clamp(1.16rem, 2.2vw, 1.56rem);
      line-height: 1.04;
      letter-spacing: -0.02em;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 7px;
      padding: 6px 9px;
    }}
    .topbar-actions {{
      display: flex;
      align-items: center;
      gap: 4px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .topbar-actions button {{
      min-height: 28px;
      padding: 4px 8px;
      font-size: 0.74rem;
    }}
    .topbar-actions .button-link {{
      min-height: 28px;
      padding: 4px 8px;
      font-size: 0.74rem;
    }}
    .topbar-actions .utility-button {{
      min-width: 0;
    }}
    .status-copy {{
      color: var(--muted);
      margin: 2px 0 0;
      font-size: 0.73rem;
      line-height: 1.28;
      max-width: 34rem;
    }}
    .version-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 7px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--muted);
      font-size: 0.66rem;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }}
    .console-nav {{
      display: flex;
      gap: 6px;
      align-items: center;
      overflow-x: auto;
      padding: 2px 2px 4px;
      scrollbar-width: none;
      -webkit-overflow-scrolling: touch;
    }}
    .console-nav::-webkit-scrollbar {{
      display: none;
    }}
    .console-nav-label {{
      color: var(--muted);
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 0 4px;
      white-space: nowrap;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 0.74rem;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }}
    .pill::before {{
      content: "";
      width: 0.7rem;
      height: 0.7rem;
      border-radius: 999px;
      flex: 0 0 auto;
      background: currentColor;
      opacity: 0.9;
    }}
    .pill.idle {{
      background: var(--surface-2);
      color: var(--muted);
      border-color: var(--border);
    }}
    .pill.running {{
      background: var(--surface-2);
      color: var(--warn);
      border-color: var(--border);
    }}
    .pill.ok {{
      background: var(--surface-2);
      color: var(--accent-2);
      border-color: var(--border);
    }}
    .pill.error {{
      background: var(--surface-2);
      color: var(--danger);
      border-color: var(--border);
    }}
    .pill.running::before,
    button.primary.pending::before,
    .message.pending .message-body::before {{
      content: "";
      width: 0.72rem;
      height: 0.72rem;
      border-radius: 999px;
      border: 2px solid currentColor;
      border-right-color: transparent;
      background: transparent;
      display: inline-block;
      vertical-align: -0.1rem;
      animation: spin 0.8s linear infinite;
    }}
    .pill.running::before {{
      margin-right: 2px;
    }}
    button,
    .button-link {{
      appearance: none;
      border: 1px solid var(--border);
      background: var(--surface-2);
      color: var(--text);
      border-radius: 999px;
      padding: 6px 10px;
      font: inherit;
      font-weight: 545;
      cursor: pointer;
      min-height: 32px;
      transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
    }}
    .button-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      white-space: nowrap;
    }}
    button.primary {{
      background: linear-gradient(180deg, var(--surface-3), var(--surface-2));
      color: var(--text);
      border-color: var(--border-strong);
    }}
    button:hover,
    .button-link:hover {{
      background: var(--surface-3);
      border-color: var(--border-strong);
    }}
    button.primary.pending {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .ghost {{
      background: transparent;
    }}
    button.warn {{
      color: var(--warn);
    }}
    button.danger {{
      color: var(--danger);
    }}
    button:disabled {{
      opacity: 0.6;
      cursor: wait;
    }}
    .hint {{
      color: var(--muted);
      font-size: 0.88rem;
    }}
    #transport-state[data-connected="true"] {{
      color: var(--accent-2);
      font-weight: 700;
    }}
    .workspace {{
      flex: 1;
      min-height: 0;
      display: grid;
      gap: 8px;
      position: relative;
    }}
    .chat-shell {{
      min-height: 0;
      display: flex;
      flex-direction: column;
      padding: 8px;
      position: relative;
    }}
    .chat-main {{
      flex: 1;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding-right: 2px;
      scrollbar-gutter: stable;
      -webkit-overflow-scrolling: touch;
      scroll-behavior: smooth;
      overscroll-behavior-y: auto;
      touch-action: pan-y;
    }}
    .chat-main:focus {{
      outline: none;
    }}
    .chat-summary-bar {{
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
      align-items: center;
      padding-bottom: 3px;
    }}
    .meta-block {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      min-width: 0;
    }}
    .meta-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      background: var(--surface-2);
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.68rem;
      line-height: 1.1;
    }}
    .meta-chip.strong {{
      background: var(--surface-3);
      border-color: var(--border-strong);
      color: var(--text);
    }}
    .meta-chip.subtle {{
      background: transparent;
    }}
    .conversation {{
      display: flex;
      flex-direction: column;
      gap: 5px;
      padding: 2px 0 8px 0;
      min-height: min-content;
      touch-action: pan-y;
    }}
    .history-toolbar {{
      display: none;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      padding: 2px 0 4px;
    }}
    .history-inline-teaser {{
      align-self: center;
      min-height: 28px;
      padding: 5px 9px;
      border-radius: 999px;
      font-size: 0.76rem;
      color: var(--muted);
      background: var(--surface-2);
    }}
    .history-toolbar.visible {{
      display: flex;
    }}
    .history-note {{
      color: var(--muted);
      font-size: 0.73rem;
    }}
    .history-toggle {{
      min-height: 27px;
      padding: 4px 8px;
      font-size: 0.73rem;
    }}
    .profile-chip,
    .quick-link {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 5px 9px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface-2);
      color: var(--muted);
      text-decoration: none;
      font-size: 0.74rem;
      white-space: nowrap;
    }}
    .profile-chip.active {{
      color: var(--text);
      border-color: var(--border-strong);
      background: var(--surface-3);
    }}
    .timeline-divider {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      padding: 4px 0;
    }}
    .timeline-divider::before,
    .timeline-divider::after {{
      content: "";
      height: 1px;
      flex: 1;
      background: var(--border);
    }}
    .message {{
      align-self: flex-start;
      max-width: min(92%, 760px);
      border-radius: 14px;
      border: 1px solid var(--border);
      background: var(--surface-2);
      padding: 8px 10px;
      box-shadow: none;
    }}
    .message.user {{
      align-self: flex-end;
      background: var(--surface-3);
      border-color: var(--border-strong);
    }}
    .message.assistant {{
      max-width: min(94%, 820px);
      background: var(--surface);
      border-color: var(--border);
      padding: 8px 10px;
    }}
    .message.latest-message {{
      position: relative;
    }}
    .message.latest-message::after {{
      content: "";
      position: absolute;
      inset: -3px -2px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(155, 193, 214, 0.06), rgba(155, 193, 214, 0));
      pointer-events: none;
    }}
    .message.assistant.latest-message::after {{
      inset: -1px -10px -1px -8px;
      border-radius: 18px;
    }}
    .message.error {{
      background: var(--surface-2);
      border-color: var(--danger);
    }}
    .message.pending {{
      border-style: dashed;
      background: var(--surface-2);
      border-color: var(--warn);
    }}
    .message.queued {{
      border-style: dashed;
      background: var(--surface-2);
    }}
    .message.empty {{
      align-self: stretch;
      max-width: none;
      color: var(--muted);
      text-align: center;
      font-style: italic;
      padding: 15px;
      background: var(--bg-soft);
    }}
    .message-head {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 3px;
      color: var(--muted);
      font-size: 0.61rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      text-transform: none;
    }}
    .message.user .message-head {{
      display: none;
    }}
    .message.assistant .message-head,
    .message.error .message-head,
    .message.pending .message-head,
    .message.queued .message-head {{
      margin-bottom: 4px;
    }}
    .message-body {{
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.5;
      font-size: 0.92rem;
      user-select: text;
      -webkit-user-select: text;
    }}
    .message-body a {{
      color: var(--accent);
      text-decoration: underline;
      text-decoration-color: currentColor;
      text-decoration-thickness: 0.07em;
      text-underline-offset: 0.14em;
      overflow-wrap: anywhere;
      cursor: pointer;
      font-weight: 550;
    }}
    .message-body a:hover {{
      text-decoration: underline;
    }}
    .message-body a.file-link,
    .raw-view a.file-link {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-weight: 620;
    }}
    .message-body a.file-link::before,
    .raw-view a.file-link::before {{
      content: "↗";
      font-size: 0.78em;
      opacity: 0.74;
    }}
    .message-body code {{
      font-family: "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 0.9em;
      padding: 0.1rem 0.35rem;
      border-radius: 0.4rem;
      background: var(--bg-soft);
    }}
    .message-footer {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 5px;
      margin-top: 6px;
    }}
    .message-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-top: 0;
    }}
    .link-chip-row {{
      display: inline-flex;
      align-items: center;
      gap: 0;
      min-width: 0;
      max-width: 100%;
    }}
    .link-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      max-width: min(100%, 320px);
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--accent);
      text-decoration: none;
      font-size: 0.74rem;
      line-height: 1.2;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: background 0.12s ease, border-color 0.12s ease;
    }}
    .link-chip:hover {{
      background: var(--surface-3);
      border-color: var(--border-strong);
    }}
    .link-copy-button {{
      min-height: 24px;
      padding: 3px 6px;
      font-size: 0.73rem;
    }}
    .message .link-copy-button {{
      display: none;
    }}
    .message.pending .message-body {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .activity-strip {{
      display: none;
      align-items: flex-start;
      gap: 9px;
      min-height: 30px;
      padding: 5px 7px;
      border-radius: 12px;
      background: var(--surface-2);
      border: 1px solid var(--border);
    }}
    .activity-strip.visible {{
      display: flex;
    }}
    .activity-strip.working {{
      border-left: 3px solid var(--warn);
    }}
    .activity-strip.console {{
      border-left: 3px solid var(--accent-2);
    }}
    .activity-strip.queue {{
      border-left: 3px solid var(--accent);
    }}
    .activity-icon {{
      width: 0.8rem;
      height: 0.8rem;
      margin-top: 0.22rem;
      border-radius: 999px;
      flex: 0 0 auto;
      background: currentColor;
      opacity: 0.88;
    }}
    .activity-strip.working .activity-icon {{
      width: 0.86rem;
      height: 0.86rem;
      border: 2px solid currentColor;
      border-right-color: transparent;
      background: transparent;
      animation: spin 0.9s linear infinite;
    }}
    .activity-copy {{
      min-width: 0;
      display: grid;
      gap: 2px;
    }}
    .activity-title {{
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--text);
    }}
    .activity-detail {{
      font-size: 0.76rem;
      color: var(--muted);
      line-height: 1.4;
      word-break: break-word;
    }}
    .composer-wrap {{
      display: grid;
      gap: 4px;
      padding-top: 5px;
      border-top: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, var(--bg) 22%, var(--bg) 100%);
    }}
    .response-bar {{
      display: flex;
      align-items: center;
      gap: 7px;
      flex-wrap: wrap;
      padding: 1px 0 2px;
    }}
    .response-summary {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      margin-left: auto;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--muted);
      font-size: 0.72rem;
      line-height: 1;
    }}
    .response-speed {{
      display: inline-flex;
      align-items: center;
      gap: 2px;
      padding: 2px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--bg-soft);
      flex: 0 0 auto;
      overflow-x: auto;
      max-width: 100%;
      scrollbar-width: none;
    }}
    .response-speed::-webkit-scrollbar {{
      display: none;
    }}
    .response-button {{
      min-height: 24px;
      padding: 2px 9px;
      border-radius: 999px;
      font-size: 0.72rem;
      line-height: 1;
      white-space: nowrap;
      border-color: transparent;
      background: transparent;
    }}
    .response-button.active {{
      background: var(--surface-3);
      border-color: var(--border-strong);
      color: var(--text);
    }}
    .response-depth {{
      flex: 1 1 148px;
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 28px;
      padding: 2px 9px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
    }}
    .response-depth-copy {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      flex: 0 0 auto;
      color: var(--muted);
      font-size: 0.71rem;
      line-height: 1;
      white-space: nowrap;
    }}
    .response-depth-copy strong {{
      color: var(--text);
      font-size: 0.72rem;
    }}
    .response-range {{
      flex: 1 1 auto;
      min-width: 70px;
      margin: 0;
      accent-color: var(--accent);
    }}
    .suggestions {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }}
    .suggestion-chip {{
      min-height: 24px;
      padding: 3px 7px;
      border-radius: 999px;
      font-size: 0.71rem;
      background: var(--surface-2);
    }}
    .composer {{
      display: grid;
      gap: 0;
    }}
    .composer-input-shell {{
      position: relative;
    }}
    textarea {{
      width: 100%;
      min-height: 54px;
      resize: none;
      overflow-y: hidden;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: var(--bg-soft);
      color: var(--text);
      font: inherit;
      line-height: 1.5;
      padding: 10px 88px 30px 11px;
      margin: 0;
    }}
    textarea:focus-visible,
    button:focus-visible,
    a:focus-visible,
    summary:focus-visible {{
      outline: 2px solid rgba(125, 211, 252, 0.4);
      outline-offset: 2px;
    }}
    .composer-utility {{
      position: absolute;
      left: 12px;
      bottom: 8px;
      color: var(--muted);
      font-size: 0.72rem;
      pointer-events: none;
    }}
    .composer-send {{
      position: absolute;
      right: 8px;
      bottom: 8px;
      min-height: 30px;
      padding: 4px 10px;
      font-size: 0.76rem;
    }}
    .button-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .copy-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 6px;
    }}
    .copy-button {{
      min-height: 30px;
      padding: 5px 8px;
      font-size: 0.77rem;
      opacity: 0.82;
      transition: opacity 0.12s ease, background 0.12s ease;
    }}
    .message-footer .copy-button,
    .message-footer .link-chip,
    .message-footer .link-copy-button {{
      opacity: 0.96;
    }}
    .inline-action {{
      min-height: 30px;
      padding: 5px 8px;
      border-radius: 999px;
      font-size: 0.76rem;
    }}
    .message:hover .copy-button,
    .message:focus-within .copy-button,
    .copy-button:hover {{
      opacity: 1;
    }}
    .raw-view {{
      margin: 0;
      padding: 9px 10px;
      border-radius: 13px;
      background: var(--bg-soft);
      border: 1px solid var(--border);
      white-space: pre-wrap;
      word-break: break-word;
      overflow: auto;
      max-height: 22vh;
      font-size: 0.88rem;
      line-height: 1.5;
      scrollbar-gutter: stable;
      -webkit-overflow-scrolling: touch;
      overscroll-behavior: contain;
    }}
    .raw-view a {{
      color: var(--accent);
      text-decoration: underline;
      text-decoration-color: currentColor;
      text-underline-offset: 0.14em;
      overflow-wrap: anywhere;
      cursor: pointer;
      font-weight: 550;
    }}
    .raw-links {{
      margin-top: 8px;
    }}
    .jump-latest {{
      position: absolute;
      right: 10px;
      bottom: 88px;
      z-index: 5;
      display: none;
      align-items: center;
      gap: 6px;
      min-height: 30px;
      padding: 5px 9px;
      border-radius: 999px;
      background: var(--surface);
      box-shadow: 0 8px 18px rgba(0, 0, 0, 0.2);
      font-size: 0.73rem;
    }}
    .jump-latest.visible {{
      display: inline-flex;
    }}
    .system-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.48);
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.18s ease;
      z-index: 30;
    }}
    .settings-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.38);
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.18s ease;
      z-index: 45;
    }}
    .settings-panel {{
      position: fixed;
      right: 12px;
      top: 78px;
      width: min(100vw - 24px, 340px);
      display: grid;
      gap: 12px;
      padding: 14px;
      z-index: 50;
      opacity: 0;
      pointer-events: none;
      transform: translateY(-8px);
      transition: opacity 0.18s ease, transform 0.18s ease;
    }}
    body.settings-open .settings-backdrop {{
      opacity: 1;
      pointer-events: auto;
    }}
    body.settings-open .settings-panel {{
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0);
    }}
    .settings-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }}
    .settings-head h2 {{
      margin: 0;
      font-size: 0.98rem;
      line-height: 1.2;
    }}
    .settings-head p {{
      margin: 4px 0 0;
    }}
    .settings-card {{
      display: grid;
      gap: 8px;
    }}
    .settings-label {{
      color: var(--muted);
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .settings-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }}
    .setting-pill {{
      min-height: 30px;
      padding: 5px 9px;
      font-size: 0.76rem;
    }}
    .setting-pill.active {{
      background: var(--surface-3);
      border-color: var(--border-strong);
      color: var(--text);
    }}
    .settings-note {{
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    .system-panel {{
      min-height: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      z-index: 40;
    }}
    .system-panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      padding: 14px 14px 0;
    }}
    .system-panel-head h2,
    .system-card h2 {{
      margin: 0;
      font-size: 1rem;
      line-height: 1.2;
    }}
    .system-panel-body {{
      display: grid;
      gap: 14px;
      overflow: auto;
      padding: 12px 14px 14px;
      scrollbar-gutter: stable;
      -webkit-overflow-scrolling: touch;
    }}
    .system-card {{
      display: grid;
      gap: 10px;
      min-width: 0;
      padding-top: 12px;
      border-top: 1px solid var(--border);
    }}
    .system-card:first-child {{
      padding-top: 0;
      border-top: 0;
    }}
    .system-card h3 {{
      margin: 0;
      font-size: 0.76rem;
      line-height: 1.2;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .system-card-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
    }}
    .raw-grid {{
      display: grid;
      gap: 10px;
    }}
    .mono {{
      font-family: "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
    }}
    .subtle {{
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .system-note {{
      font-size: 0.84rem;
      color: var(--muted);
    }}
    .services {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .service-chip {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border-radius: 999px;
      padding: 7px 10px;
      background: var(--surface-2);
      color: var(--muted);
      border: 1px solid var(--border);
      font-size: 0.82rem;
    }}
    .service-chip::before {{
      content: "";
      width: 0.55rem;
      height: 0.55rem;
      border-radius: 999px;
      background: currentColor;
      opacity: 0.72;
      flex: 0 0 auto;
    }}
    .service-chip.active {{
      color: var(--accent-2);
      border-color: var(--border);
    }}
    .service-chip.failed,
    .service-chip.inactive {{
      color: var(--danger);
      border-color: var(--danger);
    }}
    .service-chip.activating,
    .service-chip.deactivating {{
      color: var(--warn);
      border-color: var(--warn);
    }}
    details {{
      border-top: 1px solid var(--border);
      padding-top: 10px;
    }}
    details:first-of-type {{
      border-top: 0;
      padding-top: 0;
    }}
    details summary {{
      cursor: pointer;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    pre {{
      margin: 0;
      padding: 10px 11px;
      border-radius: 14px;
      background: var(--bg-soft);
      border: 1px solid var(--border);
      white-space: pre-wrap;
      word-break: break-word;
      overflow: auto;
      max-height: 22vh;
      font-size: 0.86rem;
      font-family: "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
      scrollbar-gutter: stable;
      -webkit-overflow-scrolling: touch;
      overscroll-behavior: contain;
    }}
    pre,
    textarea {{
      user-select: text;
      -webkit-user-select: text;
    }}
    @keyframes spin {{
      to {{
        transform: rotate(360deg);
      }}
    }}
    @media (min-width: 980px) {{
      .workspace {{
        grid-template-columns: minmax(0, 1fr) 336px;
      }}
      .chat-shell,
      .system-panel {{
        min-height: calc(100dvh - 104px);
      }}
      .system-panel {{
        position: sticky;
        top: 0;
      }}
      .system-toggle,
      .system-close,
      .system-backdrop {{
        display: none;
      }}
    }}
    @media (max-width: 979px) {{
      .app-shell {{
        padding: 8px;
      }}
      .topbar {{
        align-items: flex-start;
      }}
      .topbar-actions {{
        justify-content: flex-start;
      }}
      .workspace {{
        display: block;
      }}
      .chat-shell {{
        min-height: calc(100dvh - 98px);
      }}
      .system-backdrop {{
        display: block;
      }}
      body.system-open .system-backdrop {{
        opacity: 1;
        pointer-events: auto;
      }}
      .system-panel {{
        position: fixed;
        left: 10px;
        right: 10px;
        bottom: 10px;
        max-height: min(84dvh, 820px);
        transform: translateY(calc(100% + 18px));
        opacity: 0;
        pointer-events: none;
        transition: transform 0.2s ease, opacity 0.2s ease;
      }}
      body.system-open .system-panel {{
        transform: translateY(0);
        opacity: 1;
        pointer-events: auto;
      }}
      .settings-panel {{
        left: 10px;
        right: 10px;
        top: auto;
        bottom: 10px;
        width: auto;
        transform: translateY(calc(100% + 18px));
      }}
      body.settings-open .settings-panel {{
        transform: translateY(0);
      }}
      .message {{
        max-width: 100%;
      }}
    }}
    @media (max-width: 640px) {{
      body {{
        overscroll-behavior-y: auto;
      }}
      .app-shell {{
        padding: 8px;
      }}
      .topbar,
      .chat-shell {{
        padding: 10px;
      }}
      .console-nav {{
        padding-left: 0;
        padding-right: 0;
      }}
      #transport-state,
      #last-updated-head {{
        display: none;
      }}
      #refresh-button,
      #chat-session-chip,
      .version-chip,
      .composer-utility {{
        display: none;
      }}
      .chat-summary-bar {{
        gap: 5px;
      }}
      .meta-chip {{
        font-size: 0.7rem;
      }}
      .activity-strip {{
        padding: 7px 8px;
        border-radius: 12px;
      }}
      .activity-title {{
        font-size: 0.8rem;
      }}
      .activity-detail {{
        font-size: 0.76rem;
      }}
      .system-panel-head,
      .system-panel-body {{
        padding-left: 12px;
        padding-right: 12px;
      }}
      .suggestions {{
        overflow-x: auto;
        flex-wrap: nowrap;
        padding-bottom: 2px;
      }}
      .response-speed {{
        flex: 1 1 100%;
        justify-content: flex-start;
      }}
      .response-button {{
        flex: 0 0 auto;
      }}
      .response-depth {{
        flex: 1 1 100%;
      }}
      .response-range {{
        min-width: 52px;
      }}
      .response-depth-copy span {{
        display: none;
      }}
      .response-depth {{
        padding: 2px 8px;
      }}
      .suggestion-chip {{
        flex: 0 0 auto;
      }}
      textarea {{
        min-height: 52px;
        padding-right: 74px;
        padding-bottom: 12px;
      }}
      .composer-send {{
        right: 7px;
        bottom: 7px;
        min-height: 28px;
        padding: 4px 9px;
      }}
      body[data-density="compact"] .topbar,
      body[data-density="compact"] .chat-shell {{
        padding: 10px;
      }}
      body[data-density="compact"] .brand h1 {{
        font-size: 1.12rem;
      }}
    }}
    body[data-density="compact"] .app-shell {{
      gap: 6px;
      padding: 8px;
    }}
    body[data-density="compact"] .chat-shell {{
      padding: 10px;
    }}
    body[data-density="compact"] .conversation {{
      gap: 5px;
    }}
    body[data-density="compact"] .message {{
      padding: 8px 10px;
      border-radius: 13px;
    }}
    body[data-density="compact"] .composer-wrap {{
      gap: 4px;
      padding-top: 6px;
    }}
    body[data-density="compact"] .response-bar {{
      gap: 6px;
    }}
    body[data-density="compact"] .response-depth {{
      padding: 2px 8px;
    }}
    body[data-density="compact"] textarea {{
      min-height: 50px;
      padding: 9px 84px 28px 11px;
    }}
    body[data-density="compact"] .topbar {{
      padding: 7px 10px;
    }}
  </style>
</head>
<body>
  <div class="app-shell">
    <header id="topbar" class="topbar surface">
      <div class="brand">
        <h1>{html.escape(AGENT_NAME)}</h1>
        <p id="status-message" class="status-copy">Loading current status…</p>
      </div>
      <div class="topbar-actions">
        <span id="run-state" class="pill idle">Loading</span>
        <a id="theme-toggle-button" class="ghost utility-button button-link" href="{html.escape(build_console_href(token=token_value_raw, profile=theme_toggle_target))}" title="Switch to {html.escape(theme_toggle_label)} mode">{html.escape(theme_toggle_label)}</a>
        <span class="version-chip" title="Console UI version">UI v{html.escape(UI_VERSION)}</span>
        <span id="transport-state" class="hint">Connecting live updates…</span>
        <button id="refresh-button" type="button" class="ghost utility-button">Refresh</button>
        <button id="settings-toggle-button" type="button" class="ghost utility-button">View</button>
        <button id="system-toggle-button" type="button" class="ghost utility-button system-toggle">System</button>
      </div>
    </header>
    {console_nav_html}

    <div class="workspace">
      <main id="chat-shell" class="chat-shell surface">
        <div id="chat-main" class="chat-main" tabindex="0">
          <div class="chat-summary-bar">
            <span id="chat-session-chip" class="meta-chip strong">Session loading…</span>
            <span id="chat-activity-chip" class="meta-chip">Chat activity loading…</span>
            <span id="history-summary" class="meta-chip subtle">Loading conversation…</span>
            <span id="last-updated-head" class="meta-chip subtle">loading status</span>
          </div>
          <div id="history-toolbar" class="history-toolbar">
            <span id="history-window-note" class="history-note"></span>
            <button id="history-toggle-button" type="button" class="ghost history-toggle">Show older</button>
          </div>
          <div id="conversation" class="conversation">
            <div class="message empty">Conversation will appear here.</div>
          </div>
        </div>
        <button id="jump-latest-button" type="button" class="ghost jump-latest">Latest</button>
        <div class="composer-wrap">
          <div id="activity-strip" class="activity-strip">
            <div id="activity-icon" class="activity-icon"></div>
            <div class="activity-copy">
              <div id="activity-title" class="activity-title"></div>
              <div id="activity-detail" class="activity-detail"></div>
            </div>
          </div>
          <div class="response-bar" aria-label="Response tuning">
            <div id="response-speed-row" class="response-speed">
              <button type="button" class="ghost response-button" data-setting="responseSpeed" data-value="fast">Fast</button>
              <button type="button" class="ghost response-button" data-setting="responseSpeed" data-value="balanced">Std</button>
              <button type="button" class="ghost response-button" data-setting="responseSpeed" data-value="careful">Deep</button>
            </div>
            <label class="response-depth" for="response-detail-range">
              <span class="response-depth-copy">
                <span>Detail</span>
                <strong id="response-detail-label">Balanced</strong>
              </span>
              <input id="response-detail-range" class="response-range" type="range" min="1" max="5" step="1" value="{DEFAULT_RESPONSE_DETAIL}">
            </label>
            <span id="response-summary" class="response-summary">Balanced · Balanced</span>
          </div>
          <div id="prompt-suggestions" class="suggestions">
            {prompt_suggestions_html}
          </div>
          <form id="ask-form" class="composer" method="post" action="/ask">
            <input type="hidden" name="token" value="{html.escape(TOKEN)}">
            <input type="hidden" name="profile" value="{html.escape(active_profile)}">
            <input id="prompt-speed-input" type="hidden" name="speed" value="{html.escape(DEFAULT_RESPONSE_SPEED)}">
            <input id="prompt-detail-input" type="hidden" name="detail" value="{DEFAULT_RESPONSE_DETAIL}">
            <div class="composer-input-shell">
              <textarea id="prompt-input" name="message" placeholder="{html.escape(PROMPT_PLACEHOLDER)}"></textarea>
              <span class="composer-utility">Enter sends · Shift+Enter newline</span>
              <button id="ask-button" type="submit" class="primary composer-send" title="Send prompt. Press Enter to send and Shift+Enter for a new line.">Send</button>
            </div>
          </form>
        </div>
      </main>

      <div id="system-backdrop" class="system-backdrop"></div>
      <div id="settings-backdrop" class="settings-backdrop"></div>
      <aside id="settings-panel" class="settings-panel surface" aria-hidden="true">
        <div class="settings-head">
          <div>
            <h2>View</h2>
            <p class="hint">Mode, palette, history, and reading density.</p>
          </div>
          <button id="settings-close-button" type="button" class="ghost utility-button">Close</button>
        </div>
        <section class="settings-card">
          <span class="settings-label">Mode</span>
          <div class="settings-row">{settings_mode_links_html}</div>
        </section>
        <section class="settings-card">
          <span class="settings-label">Palette</span>
          <div class="settings-row">{settings_profile_links_html}</div>
        </section>
        <section class="settings-card">
          <span class="settings-label">Phone History</span>
          <div id="mobile-turns-row" class="settings-row">
            <button type="button" class="ghost setting-pill" data-setting="mobileTurns" data-value="1">1 turn</button>
            <button type="button" class="ghost setting-pill" data-setting="mobileTurns" data-value="2">2 turns</button>
            <button type="button" class="ghost setting-pill" data-setting="mobileTurns" data-value="3">3 turns</button>
          </div>
        </section>
        <section class="settings-card">
          <span class="settings-label">Desktop History</span>
          <div id="desktop-turns-row" class="settings-row">
            <button type="button" class="ghost setting-pill" data-setting="desktopTurns" data-value="2">2 turns</button>
            <button type="button" class="ghost setting-pill" data-setting="desktopTurns" data-value="4">4 turns</button>
            <button type="button" class="ghost setting-pill" data-setting="desktopTurns" data-value="6">6 turns</button>
          </div>
        </section>
        <section class="settings-card">
          <span class="settings-label">Screen</span>
          <div id="view-mode-row" class="settings-row">
            <button type="button" class="ghost setting-pill" data-setting="viewMode" data-value="console">Console</button>
            <button type="button" class="ghost setting-pill" data-setting="viewMode" data-value="stage">Stage</button>
          </div>
        </section>
        <section class="settings-card">
          <span class="settings-label">Density</span>
          <div id="density-row" class="settings-row">
            <button type="button" class="ghost setting-pill" data-setting="density" data-value="compact">Compact</button>
            <button type="button" class="ghost setting-pill" data-setting="density" data-value="comfortable">Comfortable</button>
          </div>
          <div class="settings-note">Saved on this device for this console.</div>
        </section>
        {f'''<section class="settings-card">
          <span class="settings-label">Browse</span>
          <div class="settings-row">{settings_browse_links_html}</div>
          <div class="settings-note">Open the agent workspace and bridge state in a separate viewer tab.</div>
        </section>''' if settings_browse_links_html else ''}
      </aside>
      <aside id="system-panel" class="system-panel surface" aria-hidden="true">
        <div class="system-panel-head">
          <div>
            <h2>System</h2>
            <p class="hint">Runtime, logs, and direct operator controls.</p>
          </div>
          <button id="system-close-button" type="button" class="ghost system-close">Close</button>
        </div>
        <div id="system-panel-body" class="system-panel-body">
          <section class="system-card">
            <div class="system-card-head">
              <h2>Runtime</h2>
              <span id="thread-id-head" class="mono subtle">loading</span>
            </div>
            <div id="services" class="services"></div>
            <div id="system-summary" class="system-note">Loading runtime…</div>
            <div class="system-note">ui <strong>v{html.escape(UI_VERSION)}</strong> · tmux <strong>{html.escape(SESSION)}</strong> · web chat <strong>{html.escape(MODEL)}</strong> · tuning <strong>Fast/low ↔ Careful/xhigh</strong> · full access · <a href="/healthz{token_suffix}">healthz</a></div>
          </section>

          <section class="system-card">
            <details>
              <summary>Latest raw turn</summary>
              <div class="raw-grid">
                <div>
                  <div class="copy-row">
                    <h3>Last Prompt</h3>
                    <button id="copy-prompt-button" type="button" class="ghost copy-button">Copy</button>
                  </div>
                  <div id="last-prompt" class="raw-view mono">[loading]</div>
                  <div id="last-prompt-links" class="message-links raw-links" hidden></div>
                </div>
                <div>
                  <div class="copy-row">
                    <h3>Last Reply</h3>
                    <button id="copy-response-button" type="button" class="ghost copy-button">Copy</button>
                  </div>
                  <div id="last-response" class="raw-view">[loading]</div>
                  <div id="last-response-links" class="message-links raw-links" hidden></div>
                </div>
              </div>
            </details>
            <details id="error-details">
              <summary>Error / Warning</summary>
              <pre id="last-error">[none]</pre>
            </details>
          </section>

          <section class="system-card">
            <details>
              <summary>Operator tools</summary>
              <form id="tmux-form" method="post" action="/send">
                <input type="hidden" name="token" value="{html.escape(TOKEN)}">
                <input type="hidden" name="profile" value="{html.escape(active_profile)}">
                <textarea id="tmux-input" name="message" placeholder="Paste raw text directly into the live interactive tmux session."></textarea>
                <div class="composer-actions">
                  <span class="hint">Use this only for direct tmux control.</span>
                  <button id="tmux-send-button" type="submit">Paste Into tmux</button>
                </div>
              </form>
              <div class="button-row">
                <button id="interrupt-button" type="button" class="warn">Send Ctrl+C</button>
                <button id="restart-button" type="button" class="danger">Restart Session</button>
              </div>
              <details>
                <summary>Live tmux pane</summary>
                <pre id="pane-output">[loading]</pre>
              </details>
              <details>
                <summary>{html.escape(AGENT_NAME)} journal</summary>
                <pre id="journal-output">[loading]</pre>
              </details>
            </details>
          </section>
        </div>
      </aside>
    </div>
  </div>

  <script>
    const TOKEN = {token_value};
    const INITIAL_SNAPSHOT = {initial_snapshot};
    const AGENT_LABEL = {json.dumps(AGENT_NAME)};
    const ACTIVE_PROFILE = {active_profile_name_json};
    const ACTIVE_PROFILE_LABEL = {active_profile_label_json};
    const CHAT_MODEL = {json.dumps(MODEL)};
    const CHAT_REASONING = {json.dumps(response_reasoning_effort(DEFAULT_RESPONSE_SPEED))};
    const DEFAULT_RESPONSE_SPEED = {default_response_speed_json};
    const DEFAULT_RESPONSE_DETAIL = {default_response_detail_json};
    const RESPONSE_DETAIL_LABELS = {{
      1: "Simple",
      2: "Lean",
      3: "Balanced",
      4: "Detailed",
      5: "Deep",
    }};
    const SETTINGS_STORAGE_KEY = `${{AGENT_LABEL.toLowerCase().replace(/[^a-z0-9]+/g, "-")}}-console-settings-v1`;
    const DEFAULT_PREFERENCES = {{
      density: "compact",
      mobileTurns: 1,
      desktopTurns: 2,
      viewMode: "console",
      responseSpeed: DEFAULT_RESPONSE_SPEED,
      responseDetail: DEFAULT_RESPONSE_DETAIL,
    }};
    const state = {{
      snapshot: INITIAL_SNAPSHOT,
      pollTimer: null,
      stream: null,
      streamConnected: false,
      transientOperatorBanner: "",
      historyExpanded: false,
      deferredSnapshot: null,
      userPinnedHistory: false,
      hiddenHistoryTurns: 0,
      touchStartY: null,
      preferences: null,
    }};
    const desktopLayout = window.matchMedia("(min-width: 980px)");

    const el = {{
      runState: document.getElementById("run-state"),
      statusMessage: document.getElementById("status-message"),
      topbar: document.getElementById("topbar"),
      chatShell: document.getElementById("chat-shell"),
      chatMain: document.getElementById("chat-main"),
      promptInput: document.getElementById("prompt-input"),
      askForm: document.getElementById("ask-form"),
      askButton: document.getElementById("ask-button"),
      conversation: document.getElementById("conversation"),
      jumpLatestButton: document.getElementById("jump-latest-button"),
      historyToolbar: document.getElementById("history-toolbar"),
      historyWindowNote: document.getElementById("history-window-note"),
      historyToggleButton: document.getElementById("history-toggle-button"),
      historySummary: document.getElementById("history-summary"),
      chatSessionChip: document.getElementById("chat-session-chip"),
      chatActivityChip: document.getElementById("chat-activity-chip"),
      systemSummary: document.getElementById("system-summary"),
      activityStrip: document.getElementById("activity-strip"),
      activityTitle: document.getElementById("activity-title"),
      activityDetail: document.getElementById("activity-detail"),
      responseSummary: document.getElementById("response-summary"),
      responseDetailRange: document.getElementById("response-detail-range"),
      responseDetailLabel: document.getElementById("response-detail-label"),
      promptSpeedInput: document.getElementById("prompt-speed-input"),
      promptDetailInput: document.getElementById("prompt-detail-input"),
      promptSuggestions: document.getElementById("prompt-suggestions"),
      lastPrompt: document.getElementById("last-prompt"),
      lastPromptLinks: document.getElementById("last-prompt-links"),
      lastResponse: document.getElementById("last-response"),
      lastResponseLinks: document.getElementById("last-response-links"),
      lastError: document.getElementById("last-error"),
      errorDetails: document.getElementById("error-details"),
      copyPromptButton: document.getElementById("copy-prompt-button"),
      copyResponseButton: document.getElementById("copy-response-button"),
      services: document.getElementById("services"),
      paneOutput: document.getElementById("pane-output"),
      journalOutput: document.getElementById("journal-output"),
      refreshButton: document.getElementById("refresh-button"),
      transportState: document.getElementById("transport-state"),
      tmuxForm: document.getElementById("tmux-form"),
      tmuxInput: document.getElementById("tmux-input"),
      tmuxSendButton: document.getElementById("tmux-send-button"),
      interruptButton: document.getElementById("interrupt-button"),
      restartButton: document.getElementById("restart-button"),
      threadIdHead: document.getElementById("thread-id-head"),
      lastUpdatedHead: document.getElementById("last-updated-head"),
      settingsToggleButton: document.getElementById("settings-toggle-button"),
      settingsCloseButton: document.getElementById("settings-close-button"),
      settingsPanel: document.getElementById("settings-panel"),
      settingsBackdrop: document.getElementById("settings-backdrop"),
      systemToggleButton: document.getElementById("system-toggle-button"),
      systemCloseButton: document.getElementById("system-close-button"),
      systemPanel: document.getElementById("system-panel"),
      systemPanelBody: document.getElementById("system-panel-body"),
      systemBackdrop: document.getElementById("system-backdrop"),
    }};
    const suggestionButtons = Array.from(document.querySelectorAll("[data-suggestion]"));
    const settingButtons = Array.from(document.querySelectorAll("[data-setting]"));

    function formatTs(ts) {{
      if (!ts) return "n/a";
      try {{
        return new Date(ts * 1000).toLocaleString([], {{
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
          second: "2-digit",
        }});
      }} catch (_) {{
        return String(ts);
      }}
    }}

    function stateTone(snapshot) {{
      if (snapshot.pending) return ["running", "Running"];
      if (snapshot.last_error) return ["error", "Attention"];
      if (snapshot.state === "ok") return ["ok", "Ready"];
      if (snapshot.state === "error") return ["error", "Error"];
      return ["idle", "Idle"];
    }}

    function serviceTone(value) {{
      const clean = String(value || "").toLowerCase();
      if (clean === "active") return "active";
      if (clean === "failed" || clean === "inactive") return "failed";
      if (clean === "activating" || clean === "deactivating") return "activating";
      return "";
    }}

    function normalizeResponseSpeed(value) {{
      const clean = String(value || "").toLowerCase();
      if (["fast", "balanced", "careful"].includes(clean)) {{
        return clean;
      }}
      return DEFAULT_RESPONSE_SPEED;
    }}

    function normalizeResponseDetail(value) {{
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {{
        return Math.min(5, Math.max(1, Math.round(parsed)));
      }}
      return DEFAULT_RESPONSE_DETAIL;
    }}

    function responseSpeedLabel(value) {{
      const speed = normalizeResponseSpeed(value);
      if (speed === "fast") return "Fast";
      if (speed === "balanced") return "Balanced";
      return "Careful";
    }}

    function responseDetailLabel(value) {{
      return RESPONSE_DETAIL_LABELS[normalizeResponseDetail(value)] || RESPONSE_DETAIL_LABELS[DEFAULT_RESPONSE_DETAIL];
    }}

    function responseProfileText(speed, detail) {{
      return `${{responseSpeedLabel(speed)}} · ${{responseDetailLabel(detail)}}`;
    }}

    function activeRunningSpeed(snapshot) {{
      return normalizeResponseSpeed(snapshot.running_speed || snapshot.last_speed || DEFAULT_RESPONSE_SPEED);
    }}

    function activeRunningDetail(snapshot) {{
      return normalizeResponseDetail(snapshot.running_detail || snapshot.last_detail || DEFAULT_RESPONSE_DETAIL);
    }}

    function historyEntries(snapshot) {{
      const items = Array.isArray(snapshot.history) ? [...snapshot.history] : [];
      if (!items.length && !snapshot.pending && snapshot.last_prompt && snapshot.last_prompt !== "[no prompt yet]") {{
        items.push({{
          detail: snapshot.last_detail || DEFAULT_RESPONSE_DETAIL,
          prompt: snapshot.last_prompt,
          response: snapshot.last_response || "",
          error: snapshot.last_error || "",
          speed: snapshot.last_speed || DEFAULT_RESPONSE_SPEED,
          finished_at: snapshot.last_finished_at || 0,
          started_at: snapshot.last_started_at || 0,
          thread_id: snapshot.thread_id || "",
        }});
      }}
      return items;
    }}

    function queuedEntries(snapshot) {{
      return Array.isArray(snapshot.queued_prompts) ? snapshot.queued_prompts : [];
    }}

    function safeStorageGet(key) {{
      try {{
        return window.localStorage.getItem(key);
      }} catch (_) {{
        return null;
      }}
    }}

    function safeStorageSet(key, value) {{
      try {{
        window.localStorage.setItem(key, value);
      }} catch (_) {{
        // Ignore unavailable storage and continue with in-memory preferences.
      }}
    }}

    function normalizePreferenceNumber(value, fallback, choices) {{
      const parsed = Number(value);
      if (choices.includes(parsed)) {{
        return parsed;
      }}
      return fallback;
    }}

    function normalizePreferences(value) {{
      const base = {{
        density: "compact",
        mobileTurns: 1,
        desktopTurns: 2,
        viewMode: "console",
        responseSpeed: DEFAULT_RESPONSE_SPEED,
        responseDetail: DEFAULT_RESPONSE_DETAIL,
      }};
      const payload = value && typeof value === "object" ? value : {{}};
      const density = payload.density === "comfortable" ? "comfortable" : "compact";
      const viewMode = payload.viewMode === "stage" ? "stage" : "console";
      return {{
        density,
        mobileTurns: normalizePreferenceNumber(payload.mobileTurns, base.mobileTurns, [1, 2, 3]),
        desktopTurns: normalizePreferenceNumber(payload.desktopTurns, base.desktopTurns, [2, 4, 6]),
        viewMode,
        responseSpeed: normalizeResponseSpeed(payload.responseSpeed),
        responseDetail: normalizeResponseDetail(payload.responseDetail),
      }};
    }}

    function loadPreferences() {{
      const raw = safeStorageGet(SETTINGS_STORAGE_KEY);
      if (!raw) {{
        return normalizePreferences(DEFAULT_PREFERENCES);
      }}
      try {{
        return normalizePreferences(JSON.parse(raw));
      }} catch (_) {{
        return normalizePreferences(DEFAULT_PREFERENCES);
      }}
    }}

    function savePreferences() {{
      safeStorageSet(SETTINGS_STORAGE_KEY, JSON.stringify(state.preferences));
    }}

    function applyPreferences() {{
      document.body.dataset.density = state.preferences.density;
      document.body.dataset.viewMode = state.preferences.viewMode;
      for (const button of settingButtons) {{
        const key = button.dataset.setting;
        const value = button.dataset.value;
        const active = String(state.preferences[key]) === String(value);
        button.classList.toggle("active", active);
      }}
      el.responseDetailRange.value = String(state.preferences.responseDetail);
      el.responseDetailLabel.textContent = responseDetailLabel(state.preferences.responseDetail);
      el.promptSpeedInput.value = state.preferences.responseSpeed;
      el.promptDetailInput.value = String(state.preferences.responseDetail);
      const nextProfile = responseProfileText(
        state.preferences.responseSpeed,
        state.preferences.responseDetail
      );
      if (state.snapshot.pending) {{
        const currentProfile = responseProfileText(
          activeRunningSpeed(state.snapshot),
          activeRunningDetail(state.snapshot)
        );
        el.responseSummary.textContent = currentProfile === nextProfile
          ? currentProfile
          : `${{currentProfile}} → ${{nextProfile}}`;
      }} else {{
        el.responseSummary.textContent = nextProfile;
      }}
    }}

    function isDesktopLayout() {{
      return desktopLayout.matches;
    }}

    function recentHistoryWindow() {{
      const baseWindow = window.innerWidth <= 640
        ? state.preferences.mobileTurns
        : state.preferences.desktopTurns;
      if (state.preferences.viewMode === "stage" && isDesktopLayout()) {{
        return Math.max(baseWindow, 4);
      }}
      return baseWindow;
    }}

    function setSystemOpen(open) {{
      if (open) {{
        setSettingsOpen(false);
      }}
      const shouldOpen = Boolean(open) && !isDesktopLayout();
      document.body.classList.toggle("system-open", shouldOpen);
      el.systemPanel.setAttribute("aria-hidden", shouldOpen || isDesktopLayout() ? "false" : "true");
    }}

    function setSettingsOpen(open) {{
      if (open) {{
        setSystemOpen(false);
      }}
      const shouldOpen = Boolean(open);
      document.body.classList.toggle("settings-open", shouldOpen);
      el.settingsPanel.setAttribute("aria-hidden", shouldOpen ? "false" : "true");
    }}

    function syncSystemPanelMode() {{
      if (isDesktopLayout()) {{
        document.body.classList.remove("system-open");
        el.systemPanel.setAttribute("aria-hidden", "false");
        return;
      }}
      el.systemPanel.setAttribute("aria-hidden", document.body.classList.contains("system-open") ? "false" : "true");
    }}

    function setTransportState(label, connected) {{
      el.transportState.textContent = label;
      el.transportState.dataset.connected = connected ? "true" : "false";
    }}

    function escapeHtml(value) {{
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }}

    function normalizeUrlCandidate(value) {{
      let clean = String(value || "").trim();
      while (/[.,!?;:]$/.test(clean)) {{
        clean = clean.slice(0, -1);
      }}
      while (clean.endsWith(")") && (clean.match(/\\(/g) || []).length < (clean.match(/\\)/g) || []).length) {{
        clean = clean.slice(0, -1);
      }}
      return clean;
    }}

    function normalizeFileTarget(value) {{
      let clean = String(value || "").trim();
      while (/[.,!?;:]$/.test(clean)) {{
        clean = clean.slice(0, -1);
      }}
      return clean;
    }}

    function isFileTarget(value) {{
      const clean = normalizeFileTarget(value);
      return clean.startsWith("/") || clean.startsWith("~/") || clean.startsWith("file://");
    }}

    function buildFileViewHref(value) {{
      return `/api/file?token=${{encodeURIComponent(TOKEN)}}&profile=${{encodeURIComponent(ACTIVE_PROFILE)}}&path=${{encodeURIComponent(normalizeFileTarget(value))}}`;
    }}

    function extractUrls(value) {{
      const text = String(value || "");
      const urls = [];
      const seen = new Set();
      const push = (candidate) => {{
        const clean = normalizeUrlCandidate(candidate);
        if (!/^https?:\\/\\//i.test(clean) || seen.has(clean)) {{
          return;
        }}
        seen.add(clean);
        urls.push(clean);
      }};
      for (const match of text.matchAll(/\\[([^\\]]+)\\]\\((https?:\\/\\/[^\\s)]+)\\)/g)) {{
        push(match[2]);
      }}
      for (const match of text.matchAll(/https?:\\/\\/[^\\s<>"']+/g)) {{
        push(match[0]);
      }}
      return urls;
    }}

    function formatUrlLabel(url) {{
      try {{
        const parsed = new URL(url);
        const host = parsed.hostname.replace(/^www\\./, "");
        const detail = `${{parsed.pathname || ""}}${{parsed.search || ""}}`;
        if (!detail || detail === "/") {{
          return host;
        }}
        const compact = detail.length > 28 ? `${{detail.slice(0, 27)}}…` : detail;
        return `${{host}}${{compact}}`;
      }} catch (_) {{
        const clean = String(url || "");
        return clean.length > 40 ? `${{clean.slice(0, 39)}}…` : clean;
      }}
    }}

    function renderRichText(value) {{
      let text = escapeHtml(value || "");
      text = text.replace(
        /\\[([^\\]]+)\\]\\(([^\\s)]+)\\)/g,
        (_, label, target) => {{
          const clean = String(target || "").trim();
          if (/^https?:\\/\\//i.test(clean)) {{
            const url = normalizeUrlCandidate(clean);
            return `<a href="${{escapeHtml(url)}}" target="_blank" rel="noreferrer">${{label}}</a>`;
          }}
          if (isFileTarget(clean)) {{
            return `<a class="file-link" href="${{escapeHtml(buildFileViewHref(clean))}}" target="_blank" rel="noreferrer">${{label}}</a>`;
          }}
          return `[${{label}}](${{escapeHtml(clean)}})`;
        }}
      );
      text = text.replace(
        /(^|[\\s(])((?:\\/|~\\/)[^\\s<)"']+)/g,
        (_, prefix, target) => {{
          const clean = normalizeFileTarget(target);
          if (!isFileTarget(clean)) {{
            return `${{prefix}}${{target}}`;
          }}
          return `${{prefix}}<a class="file-link" href="${{escapeHtml(buildFileViewHref(clean))}}" target="_blank" rel="noreferrer">${{escapeHtml(clean)}}</a>`;
        }}
      );
      text = text.replace(
        /(^|[\\s(])(https?:\\/\\/[^\\s<]+)/g,
        (_, prefix, url) => {{
          const clean = normalizeUrlCandidate(url);
          const trailing = escapeHtml(url.slice(clean.length));
          return `${{prefix}}<a href="${{escapeHtml(clean)}}" target="_blank" rel="noreferrer">${{escapeHtml(clean)}}</a>${{trailing}}`;
        }}
      );
      text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
      return text.replace(/\\n/g, "<br>");
    }}

    function summarizePrompt(value, limit = 120) {{
      const clean = String(value || "").replace(/\\s+/g, " ").trim();
      if (clean.length <= limit) {{
        return clean;
      }}
      return `${{clean.slice(0, limit - 1)}}…`;
    }}

    function isConsoleAction(snapshot) {{
      return String(snapshot.last_action || "").startsWith("tmux-");
    }}

    function summarizeServices(services) {{
      const items = Array.isArray(services) ? services : [];
      if (!items.length) return "Runtime state unavailable";
      const problems = items.filter((item) => String(item.state || "").toLowerCase() !== "active");
      if (!problems.length) return "All services healthy";
      if (problems.length === 1) {{
        return `${{problems[0].name}} ${{problems[0].state}}`;
      }}
      return `${{problems.length}} runtime issues`;
    }}

    function nodeInUi(node) {{
      if (!node) return false;
      const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
      return Boolean(
        element && element.closest("#conversation, .raw-view, pre, textarea")
      );
    }}

    function selectionActiveInUi() {{
      const selection = window.getSelection ? window.getSelection() : null;
      if (!selection || selection.isCollapsed) {{
        return false;
      }}
      return nodeInUi(selection.anchorNode) || nodeInUi(selection.focusNode);
    }}

    async function copyText(value, button) {{
      const original = button.textContent;
      try {{
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          await navigator.clipboard.writeText(value);
        }} else {{
          const helper = document.createElement("textarea");
          helper.value = value;
          helper.setAttribute("readonly", "");
          helper.style.position = "fixed";
          helper.style.opacity = "0";
          document.body.appendChild(helper);
          helper.select();
          document.execCommand("copy");
          helper.remove();
        }}
        button.textContent = "Copied";
      }} catch (_) {{
        button.textContent = "Press Ctrl+C";
      }}
      window.setTimeout(() => {{
        button.textContent = original;
      }}, 1200);
    }}

    function canConsumeScroll(node, deltaY) {{
      if (!node || !(node instanceof HTMLElement)) {{
        return false;
      }}
      const limit = node.scrollHeight - node.clientHeight;
      if (limit <= 1) {{
        return false;
      }}
      if (deltaY < 0) {{
        return node.scrollTop > 0;
      }}
      return node.scrollTop < limit - 1;
    }}

    function isNearConversationBottom() {{
      return el.chatMain.scrollTop + el.chatMain.clientHeight >= el.chatMain.scrollHeight - 72;
    }}

    function expandHistoryFromScroll() {{
      if (state.historyExpanded || state.hiddenHistoryTurns <= 0) {{
        return false;
      }}
      const previousHeight = el.chatMain.scrollHeight;
      state.historyExpanded = true;
      render(state.snapshot);
      const newHeight = el.chatMain.scrollHeight;
      el.chatMain.scrollTop = Math.max(0, newHeight - previousHeight + 28);
      return true;
    }}

    function renderLinkStrip(container, urls) {{
      container.innerHTML = "";
      if (!urls.length) {{
        container.hidden = true;
        return;
      }}
      container.hidden = false;
      for (const url of urls) {{
        const row = document.createElement("div");
        row.className = "link-chip-row";

        const link = document.createElement("a");
        link.className = "link-chip";
        link.href = url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = formatUrlLabel(url);
        link.title = url;
        row.appendChild(link);

        const copyButton = document.createElement("button");
        copyButton.type = "button";
        copyButton.className = "ghost link-copy-button";
        copyButton.textContent = "Copy";
        copyButton.addEventListener("click", () => copyText(url, copyButton));
        row.appendChild(copyButton);

        container.appendChild(row);
      }}
    }}

    function appendMessage(role, label, body, metaText, options = {{}}) {{
      const article = document.createElement("article");
      article.className = `message ${{role}}`;

      const head = document.createElement("div");
      head.className = "message-head";

      const metaWrap = document.createElement("div");
      metaWrap.className = "meta-block";

      const labelNode = document.createElement("span");
      labelNode.textContent = label;
      metaWrap.appendChild(labelNode);

      if (metaText) {{
        const metaNode = document.createElement("span");
        metaNode.textContent = metaText;
        metaWrap.appendChild(metaNode);
      }}

      head.appendChild(metaWrap);

      const text = document.createElement("div");
      text.className = "message-body";
      text.innerHTML = renderRichText(body);

      article.appendChild(head);
      article.appendChild(text);
      const urls = extractUrls(body);
      if ((role.includes("assistant") || role.includes("error")) && !role.includes("pending")) {{
        const footer = document.createElement("div");
        footer.className = "message-footer";

        const copyButton = document.createElement("button");
        copyButton.type = "button";
        copyButton.className = "ghost copy-button inline-action";
        copyButton.textContent = "Copy";
        copyButton.addEventListener("click", () => copyText(body, copyButton));
        footer.appendChild(copyButton);

        if (urls.length) {{
          const links = document.createElement("div");
          links.className = "message-links";
          renderLinkStrip(links, urls);
          footer.appendChild(links);
        }}
        article.appendChild(footer);
      }} else if (urls.length) {{
        const links = document.createElement("div");
        links.className = "message-footer";
        const linkStrip = document.createElement("div");
        linkStrip.className = "message-links";
        renderLinkStrip(linkStrip, urls);
        links.appendChild(linkStrip);
        article.appendChild(links);
      }}
      if (options.latest) {{
        article.classList.add("latest-message");
      }}
      el.conversation.appendChild(article);
      return article;
    }}

    function renderHistoryToolbar(totalTurns) {{
      const windowSize = recentHistoryWindow();
      if (totalTurns <= windowSize) {{
        el.historyToolbar.classList.remove("visible");
        el.historyWindowNote.textContent = "";
        el.historyToggleButton.textContent = "Show timeline";
        return;
      }}
      const hiddenTurns = Math.max(0, totalTurns - windowSize);
      el.historyToolbar.classList.add("visible");
      if (state.historyExpanded) {{
        el.historyWindowNote.textContent = `Full session timeline · ${{totalTurns}} turns visible.`;
        el.historyToggleButton.textContent = "Back to recent";
      }} else {{
        el.historyWindowNote.textContent = `Recent view · latest ${{windowSize}} of ${{totalTurns}} turns.`;
        el.historyToggleButton.textContent = hiddenTurns
          ? `Show timeline (${{hiddenTurns}} older)`
          : "Show timeline";
      }}
    }}

    function renderConversation(snapshot) {{
      const shouldStick = el.chatMain.scrollTop + el.chatMain.clientHeight >= el.chatMain.scrollHeight - 80;
      const items = historyEntries(snapshot);
      const queued = queuedEntries(snapshot);
      const totalTurns = items.length + (snapshot.pending ? 1 : 0);
      const windowSize = recentHistoryWindow();
      const hiddenTurns = Math.max(0, items.length - windowSize);
      const visibleItems = state.historyExpanded ? items : items.slice(-windowSize);
      state.hiddenHistoryTurns = hiddenTurns;
      const recentStartIndex = Math.max(0, items.length - windowSize);

      el.conversation.innerHTML = "";
      let latestNode = null;
      if (!items.length && !snapshot.pending) {{
        const empty = document.createElement("div");
        empty.className = "message empty";
        empty.textContent = {json.dumps(PROMPT_PLACEHOLDER)};
        el.conversation.appendChild(empty);
      }}
      if (hiddenTurns > 0 && !state.historyExpanded) {{
        const teaser = document.createElement("button");
        teaser.type = "button";
        teaser.className = "ghost history-inline-teaser";
        teaser.textContent = `Open the session timeline · ${{hiddenTurns}} earlier turn${{hiddenTurns === 1 ? "" : "s"}}`;
        teaser.addEventListener("click", () => {{
          expandHistoryFromScroll();
        }});
        el.conversation.appendChild(teaser);
      }}

      for (const [index, item] of visibleItems.entries()) {{
        if (state.historyExpanded && items.length > windowSize) {{
          if (index === 0) {{
            const earlier = document.createElement("div");
            earlier.className = "timeline-divider";
            earlier.textContent = "Earlier session";
            el.conversation.appendChild(earlier);
          }}
          if (index === recentStartIndex) {{
            const recent = document.createElement("div");
            recent.className = "timeline-divider";
            recent.textContent = "Recent";
            el.conversation.appendChild(recent);
          }}
        }}
        const promptTs = item.started_at || item.finished_at || 0;
        const replyTs = item.finished_at || item.started_at || 0;
        const responseProfile = responseProfileText(item.speed, item.detail);
        const promptMeta = promptTs ? `${{formatTs(promptTs)}} · ${{responseProfile}}` : responseProfile;
        const replyMeta = replyTs ? `${{formatTs(replyTs)}} · ${{responseProfile}}` : responseProfile;
        appendMessage("user", "You", item.prompt || "[empty prompt]", promptMeta);
        if (item.response) {{
          latestNode = appendMessage("assistant", AGENT_LABEL, item.response, replyMeta);
        }}
        if (item.error) {{
          latestNode = appendMessage("error", "Error", item.error, replyMeta);
        }}
      }}

      if (snapshot.pending && snapshot.running_prompt) {{
        const liveProfile = responseProfileText(snapshot.running_speed, snapshot.running_detail);
        const liveMeta = snapshot.last_started_at
          ? `${{formatTs(snapshot.last_started_at)}} · ${{liveProfile}}`
          : liveProfile;
        appendMessage("user", "You", snapshot.running_prompt, liveMeta);
        latestNode = appendMessage(
          "assistant pending",
          AGENT_LABEL,
          snapshot.status_message || "Working…",
          `live · ${{liveProfile}}`,
          {{ latest: true }}
        );
      }}

      for (const item of queued) {{
        const queuedProfile = responseProfileText(item.speed, item.detail);
        const queuedMeta = item.queued_at
          ? `queued ${{formatTs(item.queued_at)}} · ${{queuedProfile}}`
          : `queued · ${{queuedProfile}}`;
        appendMessage("user queued", "You", item.prompt || "[empty prompt]", queuedMeta);
      }}

      const visibleTurns = visibleItems.length + (snapshot.pending ? 1 : 0);
      const queueCount = queued.length;
      renderHistoryToolbar(totalTurns);
      if (!totalTurns && !queueCount) {{
        el.historySummary.textContent = "No conversation yet.";
      }} else if (hiddenTurns && !state.historyExpanded) {{
        el.historySummary.textContent = `${{visibleTurns}} recent of ${{totalTurns}} turns${{queueCount ? ` · ${{queueCount}} queued` : ""}}`;
      }} else if (queueCount) {{
        el.historySummary.textContent = `${{totalTurns}} turn${{totalTurns === 1 ? "" : "s"}} · ${{queueCount}} queued`;
      }} else {{
        el.historySummary.textContent = `${{totalTurns}} turn${{totalTurns === 1 ? "" : "s"}}`;
      }}

      if ((shouldStick || snapshot.pending) && !state.historyExpanded) {{
        el.chatMain.scrollTop = el.chatMain.scrollHeight;
      }}
      el.jumpLatestButton.classList.toggle("visible", !state.historyExpanded && !isNearConversationBottom() && totalTurns > 0);
      if (latestNode && !snapshot.pending && !state.historyExpanded && (shouldStick || !state.userPinnedHistory)) {{
        latestNode.classList.add("latest-message");
      }}
    }}

    function recentConsoleAction(snapshot) {{
      return (
        isConsoleAction(snapshot)
        && Number(snapshot.last_action_at || 0) > 0
        && ((Date.now() / 1000) - Number(snapshot.last_action_at || 0)) < 900
      );
    }}

    function renderActivityStrip(snapshot) {{
      const queueDepth = Number(snapshot.queue_depth || 0);
      const consoleActionActive = recentConsoleAction(snapshot);
      let mode = "";
      let title = "";
      let detail = "";

      if (snapshot.pending) {{
        mode = "working";
        title = "Running now";
        const parts = [];
        parts.push(responseProfileText(snapshot.running_speed, snapshot.running_detail));
        if (snapshot.running_prompt) {{
          parts.push(summarizePrompt(snapshot.running_prompt, window.innerWidth <= 640 ? 72 : 110));
        }}
        if (snapshot.last_started_at) {{
          parts.push(`started ${{formatTs(snapshot.last_started_at)}}`);
        }}
        if (queueDepth > 0) {{
          parts.push(queueDepth === 1 ? "1 follow-up queued" : `${{queueDepth}} follow-ups queued`);
        }}
        detail = parts.join(" · ") || "Still working.";
      }} else if (state.transientOperatorBanner || consoleActionActive) {{
        mode = "console";
        title = "Console";
        if (state.transientOperatorBanner) {{
          detail = state.transientOperatorBanner;
        }} else {{
          const parts = [snapshot.last_action_detail || "Recent console action completed."];
          if (snapshot.last_action_at) {{
            parts.push(formatTs(snapshot.last_action_at));
          }}
          detail = parts.join(" · ");
        }}
      }} else if (queueDepth > 0) {{
        mode = "queue";
        title = "Queued";
        detail = queueDepth === 1 ? "1 prompt is waiting to run next." : `${{queueDepth}} prompts are waiting to run next.`;
      }}

      if (!mode) {{
        el.activityStrip.className = "activity-strip";
        el.activityStrip.classList.remove("visible");
        el.activityTitle.textContent = "";
        el.activityDetail.textContent = "";
        return;
      }}
      el.activityStrip.className = `activity-strip visible ${{mode}}`;
      el.activityTitle.textContent = title;
      el.activityDetail.textContent = detail;
    }}

    function renderSuggestions(snapshot) {{
      const activeCount = historyEntries(snapshot).length + queuedEntries(snapshot).length + (snapshot.pending ? 1 : 0);
      el.promptSuggestions.hidden = activeCount > 0 || state.preferences.viewMode === "stage";
    }}

    function setBusyButtons(isBusy) {{
      el.askButton.disabled = isBusy;
      if (isBusy) {{
        el.askButton.textContent = state.snapshot.pending ? "Queue…" : "Sending…";
      }} else {{
        el.askButton.textContent = state.snapshot.pending ? "Queue" : "Send";
      }}
      el.askButton.classList.toggle("pending", isBusy);
      el.tmuxSendButton.disabled = isBusy;
      el.interruptButton.disabled = isBusy;
      el.restartButton.disabled = isBusy;
      el.refreshButton.disabled = isBusy;
    }}

    function autoresize(textarea) {{
      textarea.style.height = "auto";
      const target = Math.min(Math.max(textarea.scrollHeight, 64), 180);
      textarea.style.height = `${{target}}px`;
    }}

    function render(snapshot) {{
      state.snapshot = snapshot;
      const [tone, label] = stateTone(snapshot);
      el.runState.className = `pill ${{tone}}`;
      el.runState.textContent = label;
      const queueDepth = Number(snapshot.queue_depth || 0);
      const consoleActionActive = recentConsoleAction(snapshot);
      let statusText = snapshot.status_message || "Ready.";
      if (snapshot.pending && snapshot.running_prompt) {{
        statusText = `Working on: ${{summarizePrompt(snapshot.running_prompt, 92)}} · ${{responseProfileText(snapshot.running_speed, snapshot.running_detail)}}`;
      }} else if (consoleActionActive) {{
        statusText = snapshot.last_action_detail
          ? `Console action: ${{snapshot.last_action_detail}}`
          : "Recent console action completed.";
      }} else if (snapshot.last_finished_at) {{
        statusText = `Ready · last reply ${{formatTs(snapshot.last_finished_at)}} · ${{responseProfileText(snapshot.last_speed, snapshot.last_detail)}}`;
      }}
      if (snapshot.pending && queueDepth > 0) {{
        statusText += ` ${{
          queueDepth === 1 ? "1 follow-up queued." : `${{queueDepth}} follow-ups queued.`
        }}`;
      }}
      el.statusMessage.textContent = statusText;

      el.threadIdHead.textContent = snapshot.thread_id || "thread not started";
      el.lastUpdatedHead.textContent = snapshot.updated_at ? `updated ${{formatTs(snapshot.updated_at)}}` : "waiting for first update";
      el.systemSummary.textContent = summarizeServices(snapshot.services);
      const sessionProfile = snapshot.pending
        ? responseProfileText(snapshot.running_speed, snapshot.running_detail)
        : responseProfileText(state.preferences.responseSpeed, state.preferences.responseDetail);
      el.chatSessionChip.textContent = snapshot.thread_id
        ? `${{CHAT_MODEL}} · ${{sessionProfile}} · ${{snapshot.thread_id.slice(0, 8)}}…`
        : `${{CHAT_MODEL}} · ${{sessionProfile}} · ${{ACTIVE_PROFILE_LABEL}}`;
      if (snapshot.pending) {{
        el.chatActivityChip.textContent = queueDepth > 0
          ? `Working · ${{responseProfileText(snapshot.running_speed, snapshot.running_detail)}} · ${{queueDepth}} queued`
          : `Working · ${{responseProfileText(snapshot.running_speed, snapshot.running_detail)}}`;
      }} else if (consoleActionActive) {{
        el.chatActivityChip.textContent = snapshot.last_action_at
          ? `Console action · ${{formatTs(snapshot.last_action_at)}}`
          : "Recent console action";
      }} else if (snapshot.last_finished_at) {{
        el.chatActivityChip.textContent = `Idle · ${{responseProfileText(snapshot.last_speed, snapshot.last_detail)}} · last reply ${{formatTs(snapshot.last_finished_at)}}`;
      }} else {{
        el.chatActivityChip.textContent = `Ready · next ${{responseProfileText(state.preferences.responseSpeed, state.preferences.responseDetail)}}`;
      }}

      el.lastError.textContent = snapshot.last_error || "[none]";
      el.copyPromptButton.disabled = !snapshot.last_prompt || snapshot.last_prompt === "[no prompt yet]";
      el.copyResponseButton.disabled = !snapshot.last_response || snapshot.last_response === "[no response yet]";
      el.errorDetails.open = Boolean(snapshot.last_error);

      const preserveSelection = selectionActiveInUi();
      if (!preserveSelection) {{
        el.lastPrompt.dataset.raw = snapshot.last_prompt || "[no prompt yet]";
        el.lastResponse.dataset.raw = snapshot.last_response || "[no response yet]";
        el.lastPrompt.innerHTML = renderRichText(el.lastPrompt.dataset.raw);
        el.lastResponse.innerHTML = renderRichText(el.lastResponse.dataset.raw);
        renderLinkStrip(el.lastPromptLinks, extractUrls(el.lastPrompt.dataset.raw));
        renderLinkStrip(el.lastResponseLinks, extractUrls(el.lastResponse.dataset.raw));
        renderConversation(snapshot);
        el.paneOutput.textContent = snapshot.pane || "[pane unavailable]";
        el.journalOutput.textContent = snapshot.logs || "[no journal output]";
        state.deferredSnapshot = null;
      }} else {{
        state.deferredSnapshot = snapshot;
      }}
      renderActivityStrip(snapshot);
      renderSuggestions(snapshot);
      applyPreferences();

      el.services.innerHTML = "";
      for (const item of snapshot.services || []) {{
        const chip = document.createElement("span");
        chip.className = `service-chip ${{serviceTone(item.state)}}`;
        chip.textContent = `${{item.name}}: ${{item.state}}`;
        el.services.appendChild(chip);
      }}

      setBusyButtons(false);
    }}

    async function fetchStatus() {{
      const res = await fetch(`/api/status?token=${{encodeURIComponent(TOKEN)}}`, {{ cache: "no-store" }});
      if (!res.ok) {{
        throw new Error(`status ${{res.status}}`);
      }}
      return await res.json();
    }}

    async function postForm(path, payload) {{
      const body = new URLSearchParams({{ token: TOKEN, ...payload }});
      const res = await fetch(path, {{
        method: "POST",
        headers: {{ "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" }},
        body,
      }});
      let data = {{}};
      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {{
        data = await res.json();
      }}
      if (!res.ok) {{
        throw new Error(data.error || `request failed (${{res.status}})`);
      }}
      return data;
    }}

    function schedulePoll(delayMs) {{
      if (state.streamConnected) {{
        clearTimeout(state.pollTimer);
        return;
      }}
      clearTimeout(state.pollTimer);
      const nextDelay = delayMs || (state.snapshot.pending ? 2000 : 6000);
      state.pollTimer = window.setTimeout(refreshStatus, nextDelay);
    }}

    function connectStream() {{
      if (!window.EventSource) {{
        setTransportState("Polling", false);
        return;
      }}
      if (state.stream) {{
        return;
      }}
      const stream = new EventSource(`/api/stream?token=${{encodeURIComponent(TOKEN)}}`);
      state.stream = stream;
      setTransportState("Connecting…", false);

      stream.addEventListener("snapshot", (event) => {{
        try {{
          const snapshot = JSON.parse(event.data);
          state.streamConnected = true;
          setTransportState(snapshot.pending ? "Live · waiting" : "Live", true);
          clearTimeout(state.pollTimer);
          render(snapshot);
        }} catch (_) {{
          // Ignore malformed event payloads and let the fallback polling recover.
        }}
      }});

      stream.onerror = () => {{
        if (state.stream) {{
          state.stream.close();
        }}
        state.stream = null;
        state.streamConnected = false;
        setTransportState("Reconnecting…", false);
        schedulePoll(900);
        window.setTimeout(connectStream, 1800);
      }};
    }}

    async function refreshStatus() {{
      try {{
        const snapshot = await fetchStatus();
        state.streamConnected = false;
        setTransportState(snapshot.pending ? "Polling · waiting" : "Polling", false);
        render(snapshot);
      }} catch (err) {{
        el.runState.className = "pill error";
        el.runState.textContent = "Offline";
        el.statusMessage.textContent = `Status refresh failed: ${{err.message}}`;
        setTransportState("Offline", false);
      }} finally {{
        schedulePoll();
      }}
    }}

    async function submitAsk(event) {{
      event.preventDefault();
      const message = el.promptInput.value.trim();
      if (!message) return;
      const speed = normalizeResponseSpeed(state.preferences.responseSpeed);
      const detail = normalizeResponseDetail(state.preferences.responseDetail);
      const responseProfile = responseProfileText(speed, detail);
      state.transientOperatorBanner = "";
      setSystemOpen(false);
      el.askButton.disabled = true;
      el.askButton.textContent = state.snapshot.pending ? "Queueing…" : "Sending…";
      el.statusMessage.textContent = state.snapshot.pending
        ? `Queueing follow-up prompt · ${{responseProfile}}…`
        : `Submitting prompt to ${{AGENT_LABEL}} · ${{responseProfile}}…`;
      try {{
        const result = await postForm("/api/ask", {{ message, speed, detail: String(detail) }});
        if (result.accepted) {{
          el.promptInput.value = "";
          autoresize(el.promptInput);
        }}
        if (result.snapshot) {{
          render(result.snapshot);
        }}
        if (!result.accepted) {{
          el.statusMessage.textContent = result.error || "A web prompt is already running.";
        }}
      }} catch (err) {{
        el.runState.className = "pill error";
        el.runState.textContent = "Error";
        el.statusMessage.textContent = `Send failed: ${{err.message}}`;
        setBusyButtons(false);
      }} finally {{
        schedulePoll(1200);
      }}
    }}

    async function submitTmux(event) {{
      event.preventDefault();
      const message = el.tmuxInput.value.trim();
      if (!message) return;
      state.transientOperatorBanner = `Console send in progress: ${{summarizePrompt(message, 88)}}`;
      renderActivityStrip(state.snapshot);
      el.statusMessage.textContent = "Sending raw text into tmux…";
      setBusyButtons(true);
      try {{
        const result = await postForm("/api/send", {{ message }});
        el.tmuxInput.value = "";
        autoresize(el.tmuxInput);
        if (result.snapshot) {{
          state.transientOperatorBanner = "";
          render(result.snapshot);
        }}
      }} catch (err) {{
        state.transientOperatorBanner = "Console action failed.";
        renderActivityStrip(state.snapshot);
        el.statusMessage.textContent = `tmux send failed: ${{err.message}}`;
        setBusyButtons(false);
      }} finally {{
        schedulePoll(1000);
      }}
    }}

    async function fireAction(path, label) {{
      state.transientOperatorBanner = label;
      renderActivityStrip(state.snapshot);
      el.statusMessage.textContent = label;
      setBusyButtons(true);
      try {{
        const result = await postForm(path, {{}});
        if (result.snapshot) {{
          state.transientOperatorBanner = "";
          render(result.snapshot);
        }}
      }} catch (err) {{
        state.transientOperatorBanner = "Console action failed.";
        renderActivityStrip(state.snapshot);
        el.runState.className = "pill error";
        el.runState.textContent = "Error";
        el.statusMessage.textContent = `${{label}} failed: ${{err.message}}`;
        setBusyButtons(false);
      }} finally {{
        schedulePoll(1000);
      }}
    }}

    el.askForm.addEventListener("submit", submitAsk);
    el.tmuxForm.addEventListener("submit", submitTmux);
    el.copyPromptButton.addEventListener("click", () => copyText(el.lastPrompt.dataset.raw || el.lastPrompt.textContent, el.copyPromptButton));
    el.copyResponseButton.addEventListener("click", () => copyText(el.lastResponse.dataset.raw || el.lastResponse.textContent, el.copyResponseButton));
    el.historyToggleButton.addEventListener("click", () => {{
      const expanding = !state.historyExpanded;
      state.historyExpanded = expanding;
      render(state.snapshot);
      el.chatMain.scrollTop = expanding ? 0 : el.chatMain.scrollHeight;
    }});
    el.settingsToggleButton.addEventListener("click", () => setSettingsOpen(true));
    el.settingsCloseButton.addEventListener("click", () => setSettingsOpen(false));
    el.settingsBackdrop.addEventListener("click", () => setSettingsOpen(false));
    el.systemToggleButton.addEventListener("click", () => setSystemOpen(true));
    el.systemCloseButton.addEventListener("click", () => setSystemOpen(false));
    el.systemBackdrop.addEventListener("click", () => setSystemOpen(false));
    el.promptInput.addEventListener("keydown", (event) => {{
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) {{
        return;
      }}
      if (!el.promptInput.value.trim()) {{
        return;
      }}
      event.preventDefault();
      el.askForm.requestSubmit();
    }});
    el.refreshButton.addEventListener("click", () => {{
      el.statusMessage.textContent = "Refreshing status…";
      refreshStatus();
    }});
    el.interruptButton.addEventListener("click", () => fireAction("/api/interrupt", "Sending Ctrl+C…"));
    el.restartButton.addEventListener("click", () => fireAction("/api/restart", "Restarting the interactive session…"));
    el.promptInput.addEventListener("input", () => autoresize(el.promptInput));
    el.tmuxInput.addEventListener("input", () => autoresize(el.tmuxInput));
    suggestionButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        el.promptInput.value = button.dataset.suggestion || "";
        autoresize(el.promptInput);
        el.promptInput.focus();
      }});
    }});
    settingButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        const key = button.dataset.setting;
        const value = button.dataset.value;
        if (!key || !value) {{
          return;
        }}
        const stringSettings = new Set(["density", "viewMode", "responseSpeed"]);
        state.preferences = normalizePreferences({{
          ...state.preferences,
          [key]: stringSettings.has(key) ? value : Number(value),
        }});
        savePreferences();
        applyPreferences();
        render(state.snapshot);
      }});
    }});
    el.responseDetailRange.addEventListener("input", () => {{
      state.preferences = normalizePreferences({{
        ...state.preferences,
        responseDetail: Number(el.responseDetailRange.value || DEFAULT_RESPONSE_DETAIL),
      }});
      applyPreferences();
    }});
    el.responseDetailRange.addEventListener("change", () => {{
      state.preferences = normalizePreferences({{
        ...state.preferences,
        responseDetail: Number(el.responseDetailRange.value || DEFAULT_RESPONSE_DETAIL),
      }});
      savePreferences();
      applyPreferences();
      render(state.snapshot);
    }});
    window.addEventListener("keydown", (event) => {{
      if (event.key === "Escape") {{
        setSettingsOpen(false);
        setSystemOpen(false);
      }}
    }});
    document.addEventListener("selectionchange", () => {{
      if (!selectionActiveInUi() && state.deferredSnapshot) {{
        const snapshot = state.deferredSnapshot;
        state.deferredSnapshot = null;
        render(snapshot);
      }}
    }});
    desktopLayout.addEventListener("change", syncSystemPanelMode);
    el.chatMain.addEventListener("wheel", (event) => {{
      if (event.ctrlKey || event.deltaY >= 0) {{
        return;
      }}
      if (state.historyExpanded || state.hiddenHistoryTurns <= 0 || el.chatMain.scrollTop > 8) {{
        return;
      }}
      if (expandHistoryFromScroll()) {{
        event.preventDefault();
      }}
    }}, {{ passive: false }});
    el.chatMain.addEventListener("touchstart", (event) => {{
      const touch = event.touches && event.touches[0];
      if (!touch) {{
        return;
      }}
      state.touchStartY = touch.clientY;
    }}, {{ passive: true }});
    el.chatMain.addEventListener("touchmove", (event) => {{
      const touch = event.touches && event.touches[0];
      if (!touch) {{
        return;
      }}
      if (state.historyExpanded || state.hiddenHistoryTurns <= 0 || el.chatMain.scrollTop > 8) {{
        return;
      }}
      if (touch.clientY - (state.touchStartY || touch.clientY) < 26) {{
        return;
      }}
      if (expandHistoryFromScroll()) {{
        state.touchStartY = touch.clientY;
      }}
    }}, {{ passive: true }});
    el.chatMain.addEventListener("scroll", () => {{
      state.userPinnedHistory = !isNearConversationBottom();
      el.jumpLatestButton.classList.toggle("visible", !state.historyExpanded && state.userPinnedHistory);
    }});
    el.jumpLatestButton.addEventListener("click", () => {{
      state.userPinnedHistory = false;
      el.chatMain.scrollTop = el.chatMain.scrollHeight;
      el.jumpLatestButton.classList.remove("visible");
    }});

    state.preferences = loadPreferences();
    applyPreferences();
    autoresize(el.promptInput);
    autoresize(el.tmuxInput);
    syncSystemPanelMode();
    render(INITIAL_SNAPSHOT);
    connectStream();
    schedulePoll(1200);
  </script>
</body>
</html>
"""
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def render_token_gate(self, params: dict[str, list[str]]) -> None:
        supplied = html.escape((params.get("token") or [""])[0])
        active_profile = normalize_profile_name((params.get("profile") or [""])[0])
        profile_field = f'<input type="hidden" name="profile" value="{html.escape(active_profile)}">'
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{html.escape(CONSOLE_TITLE)}</title>
  <style>
    :root {{
{profile_vars_css(active_profile)}
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top right, var(--glow-a), transparent 24%),
        linear-gradient(180deg, var(--body-start) 0%, var(--body-mid) 44%, var(--body-end) 100%);
      color: var(--text);
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", Helvetica, sans-serif;
      padding: 18px;
      box-sizing: border-box;
    }}
    .box {{
      width: min(100%, 520px);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 20px;
      box-shadow: var(--shadow);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(1.4rem, 3vw, 2rem);
    }}
    p {{
      margin: 0 0 14px;
      color: var(--muted);
      line-height: 1.45;
    }}
    label {{
      display: block;
      font-size: 0.88rem;
      margin-bottom: 6px;
      color: var(--muted);
    }}
    input {{
      width: 100%;
      border-radius: 16px;
      border: 1px solid var(--border);
      padding: 12px 14px;
      background: var(--surface-2);
      color: var(--text);
      font: inherit;
      box-sizing: border-box;
    }}
    button {{
      margin-top: 12px;
      min-height: 44px;
      border-radius: 999px;
      border: 1px solid var(--border-strong);
      background: linear-gradient(180deg, var(--surface-3), var(--surface-2));
      color: var(--text);
      font: inherit;
      font-weight: 600;
      padding: 10px 14px;
      cursor: pointer;
    }}
  </style>
</head>
<body>
  <div class="box">
    <h1>{html.escape(CONSOLE_TITLE)}</h1>
    <p>This console is token-protected. Open it with the `?token=` query value, or paste the token below.</p>
    <form method="get" action="/">
      {profile_field}
      <label for="token">Token</label>
      <input id="token" name="token" value="{supplied}" placeholder="Paste the {html.escape(AGENT_NAME)} web token">
      <button type="submit">Open Console</button>
    </form>
  </div>
</body>
</html>
"""
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    if HOST not in {"localhost", "127.0.0.1", "::1"} and not TOKEN:
        raise ValueError("A token is required when exposing the Codex bridge remotely")
    ensure_state_dir()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving {AGENT_NAME} Codex bridge on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
