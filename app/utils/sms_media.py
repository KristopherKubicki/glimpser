"""Render compact, stamped media assets for SMS/MMS delivery."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFile, ImageOps

from app.utils.screenshots import _is_valid_png, load_font
from app.utils.validators import validate_template_name

ImageFile.LOAD_TRUNCATED_IMAGES = True

DEFAULT_LONG_EDGE = 640
DEFAULT_MAX_BYTES = 950_000
DEFAULT_FRAMES = 5
DEFAULT_FRAME_DURATION_MS = 720
MAX_SOURCE_FRAMES = 24
MIN_LONG_EDGE = 320
MIN_FRAMES = 2


@dataclass(frozen=True)
class SmsMediaAsset:
    """Rendered SMS media plus metadata for response headers."""

    body: bytes
    content_type: str
    camera: str
    bytes: int
    frames: int
    long_edge: int
    source_age_seconds: int | None
    latest_source: str | None
    transform: str
    media_key: str
    generated_at: dt.datetime


class SmsMediaError(RuntimeError):
    """Base class for SMS media render failures."""

    status_code = 500


class InvalidSmsMediaRequest(SmsMediaError):
    """Raised when SMS media options are invalid."""

    status_code = 400


class SmsMediaNotFound(SmsMediaError):
    """Raised when no source frames exist for a camera."""

    status_code = 404


class SmsMediaStale(SmsMediaError):
    """Raised when the latest source frame is older than requested."""

    status_code = 409


class SmsMediaTooLarge(SmsMediaError):
    """Raised when an asset cannot fit under the requested byte ceiling."""

    status_code = 413


def render_sms_gif(
    camera: str,
    screenshot_root: str | os.PathLike[str],
    *,
    long_edge: int = DEFAULT_LONG_EDGE,
    max_bytes: int = DEFAULT_MAX_BYTES,
    frames: int = DEFAULT_FRAMES,
    frame_duration_ms: int = DEFAULT_FRAME_DURATION_MS,
    max_age_seconds: int | None = None,
) -> SmsMediaAsset:
    """Render a stamped, MMS-friendly GIF from recent Glimpser frames."""

    camera_name = validate_template_name(camera)
    if camera_name is None:
        raise InvalidSmsMediaRequest("invalid camera")

    long_edge, max_bytes, frames, frame_duration_ms = _bounded_sms_options(
        long_edge, max_bytes, frames, frame_duration_ms
    )
    source_dir = Path(screenshot_root) / camera_name
    source_paths = _recent_frame_paths(source_dir)
    return _render_sms_gif_from_paths(
        camera_name,
        source_paths,
        long_edge,
        max_bytes,
        frames,
        frame_duration_ms,
        max_age_seconds,
        source_kind="screenshots",
    )


def render_sms_event_buffer_gif(
    camera: str,
    event_buffer_root: str | os.PathLike[str],
    *,
    long_edge: int = DEFAULT_LONG_EDGE,
    max_bytes: int = DEFAULT_MAX_BYTES,
    frames: int = DEFAULT_FRAMES,
    frame_duration_ms: int = DEFAULT_FRAME_DURATION_MS,
    max_age_seconds: int | None = None,
) -> SmsMediaAsset:
    """Render a stamped MMS GIF from an event-buffer frame ring."""

    camera_name = validate_template_name(camera)
    if camera_name is None:
        raise InvalidSmsMediaRequest("invalid camera")

    long_edge, max_bytes, frames, frame_duration_ms = _bounded_sms_options(
        long_edge, max_bytes, frames, frame_duration_ms
    )
    source_dir = Path(event_buffer_root) / camera_name / "frames"
    source_paths = _recent_frame_paths(source_dir, suffixes={".jpg", ".jpeg"})
    return _render_sms_gif_from_paths(
        camera_name,
        source_paths,
        long_edge,
        max_bytes,
        frames,
        frame_duration_ms,
        max_age_seconds,
        source_kind="event_buffer",
    )


def _bounded_sms_options(
    long_edge: int | str | None,
    max_bytes: int | str | None,
    frames: int | str | None,
    frame_duration_ms: int | str | None,
) -> tuple[int, int, int, int]:
    long_edge = _bounded_int(long_edge, MIN_LONG_EDGE, 1280, "long_edge")
    max_bytes = _bounded_int(max_bytes, 80_000, 4_750_000, "max_bytes")
    frames = _bounded_int(frames, MIN_FRAMES, 12, "frames")
    frame_duration_ms = _bounded_int(frame_duration_ms, 120, 1200, "frame_duration_ms")
    return long_edge, max_bytes, frames, frame_duration_ms


def _render_sms_gif_from_paths(
    camera_name: str,
    source_paths: list[Path],
    long_edge: int,
    max_bytes: int,
    frames: int,
    frame_duration_ms: int,
    max_age_seconds: int | None,
    *,
    source_kind: str,
) -> SmsMediaAsset:
    if not source_paths:
        raise SmsMediaNotFound("no source frames")

    latest_path = source_paths[0]
    source_age = max(
        0, int(dt.datetime.now().timestamp() - latest_path.stat().st_mtime)
    )
    if max_age_seconds is not None and max_age_seconds > 0:
        if source_age > max_age_seconds:
            raise SmsMediaStale("latest source frame is stale")

    generated_at = dt.datetime.now(dt.timezone.utc)
    label = _camera_label(camera_name)
    stamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")

    attempts: list[tuple[int, int, int]] = []
    for candidate_edge in _edge_attempts(long_edge):
        for candidate_frames in _frame_attempts(frames):
            for colors in (96, 64, 48, 32):
                attempts.append((candidate_edge, candidate_frames, colors))

    best_body: bytes | None = None
    best_meta: tuple[int, int, int] | None = None
    for candidate_edge, candidate_frames, colors in attempts:
        paths = _sample_paths(source_paths, candidate_frames)
        rendered_frames = [
            _render_frame(
                path,
                camera_name,
                label,
                stamp,
                candidate_edge,
                colors,
                index,
                len(paths),
            )
            for index, path in enumerate(paths)
        ]
        body = _encode_gif(rendered_frames, frame_duration_ms)
        if best_body is None or len(body) < len(best_body):
            best_body = body
            best_meta = (candidate_edge, len(rendered_frames), colors)
        if len(body) <= max_bytes:
            return _asset(
                body,
                camera_name,
                latest_path,
                source_age,
                generated_at,
                candidate_edge,
                len(rendered_frames),
                colors,
                source_kind,
            )

    if best_body is not None and best_meta is not None and len(best_body) <= max_bytes:
        edge, rendered_count, colors = best_meta
        return _asset(
            best_body,
            camera_name,
            latest_path,
            source_age,
            generated_at,
            edge,
            rendered_count,
            colors,
            source_kind,
        )

    raise SmsMediaTooLarge("could not fit gif under max_bytes")


def _asset(
    body: bytes,
    camera: str,
    latest_path: Path,
    source_age: int,
    generated_at: dt.datetime,
    long_edge: int,
    frames: int,
    colors: int,
    source_kind: str,
) -> SmsMediaAsset:
    media_key = hashlib.sha256(
        f"{camera}:{latest_path.name}:{latest_path.stat().st_mtime_ns}:{len(body)}".encode()
    ).hexdigest()[:16]
    return SmsMediaAsset(
        body=body,
        content_type="image/gif",
        camera=camera,
        bytes=len(body),
        frames=frames,
        long_edge=long_edge,
        source_age_seconds=source_age,
        latest_source=latest_path.name,
        transform=(
            f"gif_{source_kind}_long_edge_{long_edge}_frames_{frames}_"
            f"colors_{colors}_slow_stamped"
        ),
        media_key=media_key,
        generated_at=generated_at,
    )


def _bounded_int(value: int | str | None, minimum: int, maximum: int, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidSmsMediaRequest(f"invalid {name}") from exc
    if parsed < minimum or parsed > maximum:
        raise InvalidSmsMediaRequest(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _recent_frame_paths(
    source_dir: Path, *, suffixes: set[str] | None = None
) -> list[Path]:
    if not source_dir.is_dir():
        return []
    suffixes = suffixes or {".png"}
    candidates = [
        path
        for path in source_dir.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.name != "latest_camera.png"
        and path.suffix.lower() in suffixes
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    valid = []
    for path in candidates[:MAX_SOURCE_FRAMES]:
        if path.stat().st_size > 0 and _is_valid_image(path):
            valid.append(path)
    return valid


def _is_valid_image(path: Path) -> bool:
    if path.suffix.lower() == ".png":
        return _is_valid_png(path.as_posix())
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception:
        return False
    return True


def _sample_paths(paths: list[Path], count: int) -> list[Path]:
    if not paths:
        return []
    ordered = list(reversed(paths[: max(count, 1)]))
    if len(ordered) >= count:
        return ordered[-count:]
    while len(ordered) < count:
        ordered.insert(0, ordered[0])
    return ordered


def _edge_attempts(long_edge: int) -> list[int]:
    edges = [long_edge, 560, 480, 400, MIN_LONG_EDGE]
    result: list[int] = []
    for edge in edges:
        bounded = max(MIN_LONG_EDGE, min(long_edge, edge))
        if bounded not in result:
            result.append(bounded)
    return result


def _frame_attempts(frames: int) -> list[int]:
    attempts = [frames, min(frames, 5), min(frames, 4), 3, MIN_FRAMES]
    result: list[int] = []
    for count in attempts:
        bounded = max(MIN_FRAMES, min(frames, count))
        if bounded not in result:
            result.append(bounded)
    return result


def _render_frame(
    path: Path,
    camera: str,
    label: str,
    stamp: str,
    long_edge: int,
    colors: int,
    index: int,
    total: int,
) -> Image.Image:
    with Image.open(path) as image:
        frame = ImageOps.exif_transpose(image).convert("RGB")
        frame.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
        frame = frame.copy()
    _apply_sms_stamp(frame, camera, label, stamp, index, total)
    return frame.convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=colors,
        dither=Image.Dither.NONE,
    )


def _apply_sms_stamp(
    image: Image.Image,
    camera: str,
    label: str,
    stamp: str,
    index: int,
    total: int,
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    pad = max(8, image.width // 48)
    bar_h = max(52, min(70, image.height // 6))
    y0 = image.height - bar_h
    pulse_alpha = _pulse_alpha(index, total)
    draw.rectangle((0, y0, image.width, image.height), fill=(0, 0, 0, 190))
    draw.rectangle((0, y0, image.width, y0 + 3), fill=(255, 205, 76, pulse_alpha))
    draw.rectangle(
        (0, 0, image.width - 1, image.height - 1),
        outline=(255, 205, 76, max(42, pulse_alpha // 3)),
        width=max(1, image.width // 220),
    )

    title_font = load_font(max(16, min(24, image.width // 25)))
    meta_font = load_font(max(12, min(16, image.width // 38)))
    title = label.upper()
    meta = f"{stamp}  |  {camera}"
    brand = "GLIMPSER"

    draw.text(
        (pad, y0 + pad - 2),
        title,
        font=title_font,
        fill=(255, 255, 255, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 220),
    )
    draw.text(
        (pad, y0 + pad + 22),
        meta,
        font=meta_font,
        fill=(220, 235, 255, 255),
    )
    _draw_progress_rail(draw, image.width, image.height, pad, index, total)

    brand_w = int(draw.textlength(brand, font=meta_font))
    draw.rounded_rectangle(
        (
            image.width - brand_w - pad * 2,
            y0 + pad,
            image.width - pad,
            y0 + pad + 20,
        ),
        radius=4,
        fill=(255, 255, 255, 36),
        outline=(255, 255, 255, 80),
    )
    draw.text(
        (image.width - brand_w - int(pad * 1.5), y0 + pad + 3),
        brand,
        font=meta_font,
        fill=(255, 255, 255, 230),
    )


def _pulse_alpha(index: int, total: int) -> int:
    if total <= 1:
        return 126
    progress = index / max(1, total - 1)
    ease = 1 - abs((progress * 2) - 1)
    return int(82 + (ease * 84))


def _draw_progress_rail(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    pad: int,
    index: int,
    total: int,
) -> None:
    if total <= 1:
        return
    rail_h = max(3, height // 130)
    gap = max(3, width // 180)
    rail_w = min(width // 3, max(72, width // 5))
    segment_w = max(5, (rail_w - gap * (total - 1)) // total)
    x0 = pad
    y0 = height - pad + 1
    for frame_index in range(total):
        x = x0 + frame_index * (segment_w + gap)
        active = frame_index <= index
        draw.rounded_rectangle(
            (x, y0, x + segment_w, y0 + rail_h),
            radius=rail_h // 2,
            fill=(255, 205, 76, 210 if active else 62),
        )


def _camera_label(camera: str) -> str:
    spaced = camera.replace("_", " ").replace("-", " ").replace(".", " ")
    label = " ".join(part for part in spaced.split() if part)
    return label or camera


def _encode_gif(frames: list[Image.Image], frame_duration_ms: int) -> bytes:
    if not frames:
        raise SmsMediaNotFound("no renderable frames")
    buffer = io.BytesIO()
    first, *rest = frames
    first.save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=rest,
        duration=_frame_durations(len(frames), frame_duration_ms),
        loop=0,
        optimize=True,
        disposal=2,
    )
    return buffer.getvalue()


def _frame_durations(frame_count: int, frame_duration_ms: int) -> list[int]:
    if frame_count <= 1:
        return [frame_duration_ms]
    linger = min(1500, max(frame_duration_ms, int(frame_duration_ms * 1.45)))
    durations = [frame_duration_ms for _ in range(frame_count)]
    durations[0] = linger
    durations[-1] = linger
    return durations
