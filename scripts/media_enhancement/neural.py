#!/usr/bin/env python3
"""Isolated CUDA pilot: tiled Real-ESRGAN and guarded RAFT midpoint synthesis.

No service credentials, prompts, face restoration, future-frame prediction or
runtime downloads. Original captures remain the only observational evidence.
"""

import argparse
import contextlib
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ESRGAN = Path("/opt/spark-media/models/realesrgan/RealESRGAN_x4plus.pth")
ESRGAN_SHA = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"  # pragma: allowlist secret -- pinned public model/code checksum
RAFT = (
    Path.home()
    / ".local/share/glimpser-enhancement-models/raft_small_C_T_V2-01064c6d.pth"
)
# Pinned official torchvision checkpoint, verified during deployment.
RAFT_SHA = "01064c6dba73b0fc9fc8edf772248560a00a3acfd62ac6677e9eeebad9680e27"  # pragma: allowlist secret -- pinned public model/code checksum


def valid_times(times, count):
    if not isinstance(times, list) or len(times) != count or not 2 <= count <= 24:
        raise ValueError("capture_times_required_for_every_source_frame")
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or v <= 0
        for v in times
    ):
        raise ValueError("invalid_capture_times")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("capture_times_must_increase")


def pair_gate(gap, change, consistency, displacement):
    """Conservative whole-pair rejection; no hidden blending on uncertain motion."""
    if not all(math.isfinite(v) for v in (gap, change, consistency, displacement)):
        return "nonfinite"
    if not 0 < gap <= 120:
        return "capture_gap"
    if change > 0.10:
        return "scene_or_exposure_change"
    if consistency < 0.96:
        return "uncertain_motion"
    if displacement > 0.08:
        return "large_motion"
    return None


def flow_geometry(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("invalid_frame_geometry")
    ratio = min(1.0, 448 / max(width, height))
    fw, fh = max(1, round(width * ratio)), max(1, round(height * ratio))
    return (
        fw,
        fh,
        max(128, math.ceil(fw / 8) * 8) - fw,
        max(128, math.ceil(fh / 8) * 8) - fh,
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gpu():
    import torch

    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise RuntimeError("personal_spark_busy_defer")
    usage = subprocess.run(
        ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    if any(int(v.strip()) > 30 for v in usage.stdout.splitlines()):
        raise RuntimeError("personal_spark_busy_defer")
    torch.set_num_threads(2)
    torch.cuda.set_per_process_memory_fraction(0.025)
    return torch


def upscaler():
    import torchvision.transforms._functional_tensor as functional_tensor

    sys.modules.setdefault(
        "torchvision.transforms.functional_tensor", functional_tensor
    )
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    if digest(ESRGAN) != ESRGAN_SHA:
        raise ValueError("unexpected_restoration_weights")
    model = RRDBNet(
        num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
    )
    return RealESRGANer(
        scale=4,
        model_path=str(ESRGAN),
        model=model,
        tile=192,
        tile_pad=16,
        pre_pad=0,
        half=True,
        device="cuda",
    )


def enhance_frame(original, engine, scale=2):
    import numpy as np
    from PIL import Image

    if scale not in (1, 2):
        raise ValueError("unsupported_restoration_scale")
    if original.shape[0] * original.shape[1] > 4_200_000 / (scale * scale):
        raise ValueError("upscale_dimensions_out_of_budget")
    restored, _ = engine.enhance(original[..., ::-1].copy(), outscale=scale)
    restored = restored[..., ::-1].copy()
    baseline = np.asarray(
        Image.fromarray(original).resize(
            (original.shape[1] * scale, original.shape[0] * scale),
            Image.Resampling.LANCZOS,
        )
    )
    return (
        np.rint(0.75 * restored.astype("float32") + 0.25 * baseline)
        .clip(0, 255)
        .astype("uint8")
    )


def upscale(source, target, scale=2, lowlight=False):
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(source) as image:
        original = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))
    result = enhance_frame(original, upscaler(), scale=scale)
    lighting = None
    if lowlight:
        from illumination import recover_lighting

        result, lighting = recover_lighting(result)
    Image.fromarray(result).save(target)
    return {
        "lighting": lighting,
        "model": "RealESRGAN_x4plus",
        "model_sha256": ESRGAN_SHA,
        "neural_blend": 0.75,
        "synthetic_frames": 0,
        "face_restoration": False,
    }


def video_upscale(source, target, times):
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(str(source))
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    valid_times(times, count)
    if count > 12 or not 0 < fps <= 15:
        raise ValueError("video_upscale_budget")
    engine = upscaler()
    folder = target.parent / "neural-frames"
    folder.mkdir()
    decoded = 0
    temporal_gains = []
    previous = None
    try:
        for index in range(count):
            ok, frame = cap.read()
            if not ok:
                raise ValueError("incomplete_source_decode")
            output = enhance_frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), engine)
            import numpy as np

            current = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype("float32") / 255
            reduced = (
                cv2.resize(
                    output,
                    (frame.shape[1], frame.shape[0]),
                    interpolation=cv2.INTER_AREA,
                ).astype("float32")
                / 255
            )
            if previous is not None:
                original_delta = float(np.abs(current - previous[0]).mean())
                restored_delta = float(np.abs(reduced - previous[1]).mean())
                temporal_gains.append(
                    round(restored_delta / max(original_delta, 1 / 255), 4)
                )
            previous = (current, reduced)
            Image.fromarray(output).save(folder / f"{index:03d}.png")
            decoded += 1
        if cap.read()[0]:
            raise ValueError("unexpected_extra_frames")
    finally:
        cap.release()
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(folder / "%03d.png"),
            "-an",
            "-vf",
            "setsar=1",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-fs",
            str(64 * 1024**2),
            "-y",
            str(target),
        ],
        capture_output=True,
        timeout=45,
        check=True,
    )
    return {
        "model": "RealESRGAN_x4plus",
        "model_sha256": ESRGAN_SHA,
        "neural_blend": 0.75,
        "synthetic_frames": 0,
        "face_restoration": False,
        "source_frames": decoded,
        "output_frames": decoded,
        "source_fps": fps,
        "output_fps": fps,
        "timeline": [
            {"type": "restored_capture", "source_index": i, "captured_at": stamp}
            for i, stamp in enumerate(times)
        ],
        "temporally_trained_restoration": False,
        "temporal_delta_gain_max": max(temporal_gains, default=0),
        "temporal_delta_gains": temporal_gains,
    }


def smooth(source, target, times, torch, factor=2):
    import cv2
    import numpy as np
    import torch.nn.functional as F
    from motion import splat_midpoint
    from torchvision.models.optical_flow import raft_small

    checksum = digest(RAFT)
    if checksum != RAFT_SHA:
        raise ValueError("unexpected_flow_weights")
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    valid_times(times, count)
    if not 0 < fps <= 15:
        raise ValueError("unsupported_source_fps")
    frames = []
    try:
        while len(frames) <= 24:
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[0] * frame.shape[1] > 1_050_000:
                raise ValueError("interpolation_dimensions_out_of_budget")
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        cap.release()
    valid_times(times, len(frames))
    if len(frames) != count:
        raise ValueError("incomplete_source_decode")
    height, width = frames[0].shape[:2]
    model = raft_small(weights=None).eval().cuda()
    model.load_state_dict(torch.load(RAFT, map_location="cpu", weights_only=True))
    fw, fh, pw, ph = flow_geometry(width, height)

    def tensor(frame):
        small = cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_AREA)
        value = (
            torch.from_numpy(small).permute(2, 0, 1)[None].cuda().float() / 127.5 - 1
        )
        return F.pad(value, (0, pw, 0, ph), mode="replicate")

    def remap(array, flow):
        yy, xx = np.mgrid[: array.shape[0], : array.shape[1]].astype("float32")
        return cv2.remap(
            array,
            xx + flow[..., 0],
            yy + flow[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

    output, timeline = [], []
    for index, first in enumerate(frames):
        output.append(first)
        timeline.append(
            {"type": "captured", "source_index": index, "captured_at": times[index]}
        )
        if index == len(frames) - 1:
            for _ in range(factor - 1):
                output.append(first)
                timeline.append(
                    {"type": "held", "source_index": index, "reason": "end_of_capture"}
                )
            break
        second = frames[index + 1]
        gap = times[index + 1] - times[index]
        change = float(np.abs(first.astype("float32") - second).mean() / 255)
        reason = pair_gate(gap, change, 1, 0)
        metrics = {"gap_seconds": gap, "mean_change": round(change, 5)}
        intermediates = [first] * (factor - 1)
        if not reason and change < 0.002:
            reason = "unchanged"
        if not reason:
            with torch.inference_mode():
                a, b = tensor(first), tensor(second)
                forward = (
                    model(a, b, num_flow_updates=12)[-1][0, :, :fh, :fw]
                    .permute(1, 2, 0)
                    .cpu()
                    .numpy()
                )
                backward = (
                    model(b, a, num_flow_updates=12)[-1][0, :, :fh, :fw]
                    .permute(1, 2, 0)
                    .cpu()
                    .numpy()
                )
            cycle = forward + remap(backward, forward)
            reverse_cycle = backward + remap(forward, backward)
            reliable_a = (np.linalg.norm(cycle, axis=2) < 1.5).astype("float32")
            reliable_b = (np.linalg.norm(reverse_cycle, axis=2) < 1.5).astype("float32")
            consistent = float(min(reliable_a.mean(), reliable_b.mean()))
            displacement = float(
                max(
                    np.quantile(np.linalg.norm(flow, axis=2), 0.99)
                    for flow in (forward, backward)
                )
                / max(fw, fh)
            )
            metrics.update(
                consistency=round(consistent, 5), displacement=round(displacement, 5)
            )
            reason = pair_gate(gap, change, consistent, displacement)
            if not reason:
                f = cv2.resize(forward, (width, height)) * np.array(
                    [width / fw, height / fh], dtype="float32"
                )
                b = cv2.resize(backward, (width, height)) * np.array(
                    [width / fw, height / fh], dtype="float32"
                )
                masks = (
                    cv2.resize(
                        reliable_a, (width, height), interpolation=cv2.INTER_NEAREST
                    ),
                    cv2.resize(
                        reliable_b, (width, height), interpolation=cv2.INTER_NEAREST
                    ),
                )
                generated = []
                coverage = []
                for step in range(1, factor):
                    frame, valid = splat_midpoint(
                        first, second, f, b, step / factor, masks
                    )
                    generated.append(frame)
                    coverage.append(valid)
                metrics["minimum_coverage"] = round(min(coverage), 5)
                if min(coverage) < 0.99:
                    reason = "uncovered_motion"
                else:
                    intermediates = generated
        for step, frame in enumerate(intermediates, 1):
            output.append(frame)
            timeline.append(
                {
                    "type": "held" if reason else "interpolated",
                    "between": [index, index + 1],
                    "fraction": step / factor,
                    "reason": reason,
                    "metrics": metrics,
                }
            )
    raw = b"".join(frame.tobytes() for frame in output)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps * factor),
            "-i",
            "pipe:0",
            "-an",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-fs",
            str(64 * 1024**2),
            "-y",
            str(target),
        ],
        input=raw,
        capture_output=True,
        timeout=45,
        check=True,
    )
    return {
        "model": "torchvision-raft-small-C_T_V2",
        "model_sha256": checksum,
        "method": "bidirectional-confidence-forward-splat-v2",
        "synthetic_frames": sum(r["type"] == "interpolated" for r in timeline),
        "timeline": timeline,
        "source_fps": fps,
        "output_fps": fps * factor,
        "source_frames": count,
        "output_frames": len(output),
        "loop_interpolation": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "profile",
        choices=[
            "neural-native",
            "neural-lowlight",
            "neural-deflare",
            "neural-retinex",
            "neural-cidnet",
            "neural-jpeg",
            "neural-temporal-denoise",
            "neural-2x",
            "neural-smooth",
            "neural-smooth4",
            "neural-video-2x",
        ],
    )
    parser.add_argument("--times", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        torch = gpu()
        with torch.inference_mode():
            if args.profile in {
                "neural-retinex",
                "neural-cidnet",
                "neural-jpeg",
                "neural-temporal-denoise",
            }:
                from restoration_models import restore

                times = json.loads(args.times.read_text()) if args.times else None
                result = restore(args.source, args.target, args.profile, torch, times)
            elif args.profile == "neural-deflare":
                from deflare import restore

                result = restore(args.source, args.target, torch)
            elif args.profile in {
                "neural-2x",
                "neural-native",
                "neural-lowlight",
                "neural-deflare",
            }:
                result = upscale(
                    args.source,
                    args.target,
                    scale=2 if args.profile == "neural-2x" else 1,
                    lowlight=args.profile == "neural-lowlight",
                )
            else:
                times = json.loads(args.times.read_text())
                if args.profile == "neural-video-2x":
                    result = video_upscale(args.source, args.target, times)
                else:
                    result = smooth(
                        args.source,
                        args.target,
                        times,
                        torch,
                        4 if args.profile == "neural-smooth4" else 2,
                    )
    result.update(
        backend="personal-spark-cuda",
        generative=True,
        review_required=True,
        elapsed_seconds=round(time.monotonic() - started, 3),
        torch_version=torch.__version__,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
