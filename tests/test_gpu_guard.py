"""Replay device disappearance without loading a GPU or touching cameras."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from app.utils import gpu_guard as guard

FIXTURE_URL = "rtsp://user:secret@x"  # pragma: allowlist secret

COMMAND = [
    "ffmpeg",
    "-hwaccel",
    "cuda",
    "-i",
    FIXTURE_URL,  # pragma: allowlist secret -- synthetic fixture
]


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "_local_fault", None)
    monkeypatch.setattr(guard, "_state_path", lambda: tmp_path / "gpu.json")
    monkeypatch.setattr(guard, "_boot_id", lambda: "boot-a")


def test_loss_retries_software_and_other_worker_observes_fault(monkeypatch):
    calls = []

    def run(command, *args, **kwargs):
        calls.append(command)
        if "cuda" in command:
            return SimpleNamespace(returncode=1), b"", b"CUDA_ERROR_NO_DEVICE"
        return SimpleNamespace(returncode=0), b"ok", b""

    monkeypatch.setattr(guard, "stream_encoder_frames", run)
    assert guard.run_capture_command(COMMAND, check=True).stdout == b"ok"
    monkeypatch.setattr(guard, "_local_fault", None)  # Another worker/startup.
    assert guard.run_capture_command(COMMAND).returncode == 0
    assert ["cuda" in c for c in calls] == [True, False, False]
    status = guard.acceleration_status({"status": "verified", "effective": "cuda"})
    assert status["status"] == "failed" and status["effective"] == "false"
    assert "secret" not in guard._state_path().read_text()


def test_camera_failure_does_not_quarantine(monkeypatch):
    monkeypatch.setattr(
        guard,
        "stream_encoder_frames",
        lambda *a, **k: (
            SimpleNamespace(returncode=1),
            b"",
            FIXTURE_URL.encode()
            + b" 404",  # pragma: allowlist secret -- synthetic fixture
        ),
    )
    with pytest.raises(subprocess.CalledProcessError) as caught:
        guard.run_capture_command(COMMAND, check=True)
    assert guard.gpu_fault() is None
    assert b"secret" not in caught.value.stderr
    assert "secret" not in str(caught.value)


def test_timeout_quarantines_and_software_timeout_is_redacted(monkeypatch):
    calls = []

    def run(command, *args, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(
            command, 1, stderr=FIXTURE_URL.encode()
        )  # pragma: allowlist secret -- synthetic fixture

    monkeypatch.setattr(guard, "stream_encoder_frames", run)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        guard.run_capture_command(COMMAND, timeout=1)
    assert len(calls) == 2 and "cuda" not in calls[1]
    assert guard.gpu_fault()
    assert "secret" not in str(caught.value)
    assert b"secret" not in caught.value.stderr


def test_old_boot_fault_does_not_poison_new_boot():
    guard._state_path().write_text(json.dumps({"boot_id": "old", "reason": "lost"}))
    assert guard.gpu_fault() is None


def test_corrupt_state_fails_closed():
    guard._state_path().write_text("broken")
    assert guard.gpu_fault()


def test_health_labels_startup_check_honestly():
    status = guard.acceleration_status({"status": "verified", "effective": "cuda"})
    assert status["basis"] == "startup_capability_check"


def test_software_timeout_does_not_disable_gpu(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(["ffmpeg"], 1)

    monkeypatch.setattr(guard, "stream_encoder_frames", run)
    with pytest.raises(subprocess.TimeoutExpired):
        guard.run_capture_command(["ffmpeg", "-i", "test"], timeout=1)
    assert guard.gpu_fault() is None


def test_archive_text_output(monkeypatch):
    monkeypatch.setattr(
        guard,
        "stream_encoder_frames",
        lambda *a, **k: (
            SimpleNamespace(returncode=0),
            b"out",
            b"https://secret.example/signed",
        ),
    )
    result = guard.run_encoder_command(["ffmpeg", "-i", "test"])
    assert result.stdout == "out" and result.stderr == "[URL]"


def test_stream_preflight_recovers_from_device_loss(monkeypatch):
    from app.utils import screenshots

    calls = []

    def run(command, *args, **kwargs):
        calls.append(command)
        error = b"CUDA_ERROR_NO_DEVICE" if "cuda" in command else b""
        return SimpleNamespace(returncode=int(bool(error))), b"", error

    monkeypatch.setattr(guard, "stream_encoder_frames", run)
    monkeypatch.setattr(screenshots, "FFMPEG_HWACCEL", "cuda")
    monkeypatch.setattr(screenshots, "_rtsp_transport_candidates", lambda url: ["tcp"])
    monkeypatch.setattr(screenshots, "_set_rtsp_transport", lambda *args: None)
    assert screenshots._ffmpeg_null_probe(
        FIXTURE_URL, 5, "test"
    )  # pragma: allowlist secret -- synthetic fixture
    assert ["cuda" in c for c in calls] == [True, False]
