"""Hash-pinned, private review recipes; preserve native geometry and provenance."""

import hashlib
import importlib.util
import math
import subprocess
import sys
from pathlib import Path

MODEL_ROOT = Path.home() / ".local/share/glimpser-enhancement-models/restoration"
PINS = {
    "cidnet": {
        "net/CIDNet.py": "dc9b9232f225f5760417175d25f8efc146f51c0acd1ee014df6b9f0a6b2e8d84",  # pragma: allowlist secret -- public model checksum
        "net/HVI_transform.py": "8be0fea6e61c51d6290722f0cf81be1f334b1b998dbfd409435343d9d4bd5bb2",  # pragma: allowlist secret -- public model checksum
        "net/transformer_utils.py": "7bfb2659e97289f0e8005935e15edbe0af3ae5ef05c50863a074fd745617b13f",  # pragma: allowlist secret -- public model checksum
        "net/LCA.py": "271f487091bd13ed211a8b0c9cb07036957ba535f5dd3aedc131498500979d26",  # pragma: allowlist secret -- public model checksum
        "model.safetensors": "1163da200c800681dcf5723c92cb9010a0d8e02da32510a10d115d2188104b69",  # pragma: allowlist secret -- public model checksum
    },
    "fastdvdnet": {
        "architecture.py": "3b38ee3892420d1bd8b0c5b9b7d09bf44931276465c66527eff7555f2fa17532",  # pragma: allowlist secret -- public model checksum
        "weights.pth": "8118974ac7defaa5037f73caf87e0cb53efcfa49ae77d55c05ab187f59e55949",  # pragma: allowlist secret -- public model checksum
    },
    "retinexformer": {
        "architecture.py": "1567c89d55285a3c1a4d4ca33f288b1fd98dc6b6bbdf971eda02d745f9087631",  # pragma: allowlist secret -- public model checksum
        "weights.pth": "539bd16c4da6179e45616329f249c4672951b1045193428e1d042c50d4b65a0b",  # pragma: allowlist secret -- public model checksum
    },
    "swinir-jpeg": {
        "architecture.py": "9e143898679ebeebc5d2fc94ad1b89c38aa4a4d43da4e0fcba0f93e476994913",  # pragma: allowlist secret -- public model checksum
        "weights.pth": "3b906265f869a90793e91f4532f7b3aa4de8146195acd156464bbe9b473a482d",  # pragma: allowlist secret -- public model checksum
    },
}


def adjacent_times(times, count):
    """Temporal models require adjacent real captures, never sparse timelapses."""
    if not isinstance(times, list) or not 5 <= count <= 24 or len(times) != count:
        raise ValueError("adjacent_frames_required")
    if any(
        type(t) not in (float, int) or not math.isfinite(t) or t <= 0 for t in times
    ):
        raise ValueError("invalid_capture_times")
    gaps = [b - a for a, b in zip(times, times[1:])]
    if any(not 0 < gap <= 0.25 for gap in gaps):
        raise ValueError("sparse_frames_not_temporal_video")
    if max(gaps) > min(gaps) * 1.1:
        raise ValueError("irregular_capture_cadence")


def load_model(name, torch, root=MODEL_ROOT):
    """Load only independently installed, hash-matching architecture and weights."""
    folder = root / name
    for filename, expected in PINS[name].items():
        p = folder / filename
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError("unexpected_restoration_asset")
    # Isolated, pinned timm/einops installation; do not alter the shared runtime.
    sys.path.insert(0, str(root / "dependencies"))
    if name == "cidnet":
        # The upstream net imports are local to this short-lived worker process.
        # Refuse an existing package rather than importing an unrelated net.
        import types

        from safetensors.torch import load_file

        if any(key == "net" or key.startswith("net.") for key in sys.modules):
            raise ValueError("cidnet_import_namespace_in_use")
        package = types.ModuleType("net")
        package.__path__ = [str(folder / "net")]
        sys.modules["net"] = package
        module = importlib.import_module("net.CIDNet")
        model = module.CIDNet(
            channels=[36, 36, 72, 144], heads=[1, 2, 4, 8], norm=False
        )
        model.load_state_dict(load_file(str(folder / "model.safetensors")), strict=True)
        model.trans.alpha_s = 1.0
        model.trans.alpha = 1.0
        model.trans.gated = True
        model.trans.gated2 = True
        return model.eval().cuda()
    spec = importlib.util.spec_from_file_location(
        "glimpser_" + name.replace("-", "_"), folder / "architecture.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if name == "fastdvdnet":
        model = module.FastDVDnet(num_input_frames=5)
    elif name == "retinexformer":
        model = module.RetinexFormer(n_feat=40, stage=1, num_blocks=[1, 2, 2])
    else:
        model = module.SwinIR(
            upscale=1,
            in_chans=3,
            img_size=126,
            window_size=7,
            img_range=255.0,
            depths=[6] * 6,
            embed_dim=180,
            num_heads=[6] * 6,
            mlp_ratio=2,
            upsampler="",
            resi_connection="1conv",
        )
    state = torch.load(folder / "weights.pth", map_location="cpu", weights_only=True)
    state = state.get("params", state)
    state = {k.removeprefix("module."): v for k, v in state.items()}
    model.load_state_dict(state, strict=True)
    return model.eval().cuda()


def tiled(frames, infer, tile, stride):
    """Blend overlapping native-resolution tiles without stretching an axis."""
    import numpy as np

    try:
        from deflare import tile_origins
    except ImportError:
        from scripts.media_enhancement.deflare import tile_origins

    h, w = frames[0].shape[:2]
    if h * w > 4_200_000 or any(f.shape != frames[0].shape for f in frames):
        raise ValueError("restoration_geometry_budget")
    ys, xs = tile_origins(h, tile, stride), tile_origins(w, tile, stride)
    if len(ys) * len(xs) > 400:
        raise ValueError("restoration_tile_budget")
    frames = [
        np.pad(f, ((0, max(0, tile - h)), (0, max(0, tile - w)), (0, 0)), mode="edge")
        for f in frames
    ]
    result = np.zeros(frames[0].shape, dtype="float32")
    coverage = np.zeros((*frames[0].shape[:2], 1), dtype="float32")
    ramp = np.maximum(np.hanning(tile), 0.05).astype("float32")
    window = (ramp[:, None] * ramp[None, :])[..., None]
    for y in ys:
        for x in xs:
            output = infer([f[y : y + tile, x : x + tile] for f in frames])
            if output.shape != (tile, tile, 3) or not np.isfinite(output).all():
                raise ValueError("invalid_restoration_output")
            result[y : y + tile, x : x + tile] += output * window
            coverage[y : y + tile, x : x + tile] += window
    if (coverage <= 0).any():
        raise ValueError("incomplete_restoration_coverage")
    return (result / coverage)[:h, :w]


def bounded_result(original, prediction):
    """Limit trial alterations; do not replace clipped white observations."""
    import numpy as np

    source = original.astype("float32") / 255
    delta = np.clip(prediction - source, -0.35, 0.35)
    out = source + 0.75 * delta
    mask = source.min(axis=2) >= 0.98
    out[mask] = source[mask]
    return np.rint(out * 255).clip(0, 255).astype("uint8")


def restore(source, target, profile, torch, times=None):
    """Run a review-only still or short adjacent-frame denoising recipe."""
    import numpy as np
    from PIL import Image

    name = {
        "neural-temporal-denoise": "fastdvdnet",
        "neural-retinex": "retinexformer",
        "neural-cidnet": "cidnet",
        "neural-jpeg": "swinir-jpeg",
    }[profile]
    if name == "cidnet":
        # The color checkpoint washed out a real monochrome night capture.
        # Reject this domain before allocating the model; originals stay intact.
        with Image.open(source) as image:
            sample = np.asarray(image.convert("RGB").resize((64, 64))).astype("float32")
        if np.percentile(sample.max(axis=2) - sample.min(axis=2), 99) <= 2:
            raise ValueError("cidnet_monochrome_not_validated")
    model = load_model(name, torch)

    def infer(frames):
        tensor = np.concatenate([f.astype("float32") / 255 for f in frames], axis=2)
        tensor = torch.from_numpy(tensor.transpose(2, 0, 1).copy()).unsqueeze(0).cuda()
        if name == "fastdvdnet":
            noise = torch.full(
                (1, 1, tensor.shape[2], tensor.shape[3]), 15 / 255, device="cuda"
            )
            output = model(tensor, noise)
        else:
            output = model(tensor)
        return output[0].clamp(0, 1).float().cpu().numpy().transpose(1, 2, 0)

    result = dict(
        model=name,
        model_sha256=PINS[name][
            "model.safetensors" if name == "cidnet" else "weights.pth"
        ],
        architecture_sha256=PINS[name][
            "net/CIDNet.py" if name == "cidnet" else "architecture.py"
        ],
        asset_sha256=PINS[name],
        review_only=True,
        review_required=True,
        neural_blend=0.75,
    )
    if name == "cidnet":
        result["controls"] = {"alpha_s": 1.0, "alpha_i": 1.0, "gamma": 1.0}
        result["checkpoint"] = "HVI-CIDNet-LOLv1-wperc"
    if name != "fastdvdnet":
        with Image.open(source) as image:
            original = np.asarray(image.convert("RGB"))
        tile, stride = (126, 98) if name == "swinir-jpeg" else (256, 192)
        prediction = tiled([original], infer, tile, stride)
        output = bounded_result(original, prediction)
        Image.fromarray(output).save(target)
        result.update(
            source_frames=1,
            mean_absolute_change=float(
                np.abs(output.astype(float) - original).mean() / 255
            ),
        )
        return result

    import cv2

    cap = cv2.VideoCapture(str(source))
    frames = []
    fps = cap.get(cv2.CAP_PROP_FPS)
    try:
        while len(frames) <= 24:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        cap.release()
    adjacent_times(times, len(frames))
    h, w = frames[0].shape[:2]
    if h * w > 1_050_000 or not 4 <= fps <= 60:
        raise ValueError("temporal_video_budget")
    if abs((times[-1] - times[0]) - (len(frames) - 1) / fps) > 0.02:
        raise ValueError("capture_cadence_does_not_match_video")
    # Reject cuts/exposure jumps rather than mixing unrelated scene content.
    if any(
        np.abs(b.astype(float) - a).mean() / 255 > 0.15
        for a, b in zip(frames, frames[1:])
    ):
        raise ValueError("scene_change_not_temporal_video")
    outputs = []
    for index, original in enumerate(frames):
        neighbors = [
            frames[min(max(index + j, 0), len(frames) - 1)] for j in (-2, -1, 0, 1, 2)
        ]
        prediction = tiled(neighbors, infer, 256, 192)
        outputs.append(bounded_result(original, prediction))
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
            f"{w}x{h}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(target),
        ],
        input=b"".join(f.tobytes() for f in outputs),
        capture_output=True,
        check=True,
        timeout=60,
    )
    result.update(
        source_frames=len(frames),
        output_frames=len(frames),
        output_fps=fps,
        noise_sigma=15,
        timeline=[
            dict(type="denoised", source_index=i, captured_at=t)
            for i, t in enumerate(times)
        ],
    )
    return result
