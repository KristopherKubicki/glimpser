"""A listed GPU codec is usable only after an actual encoder probe succeeds."""

import subprocess
from unittest.mock import Mock, patch

import pytest

from app.runtime_health import probe_acceleration


def test_verified_cuda_uses_only_a_bounded_synthetic_frame():
    with patch(
        "app.runtime_health.subprocess.run", return_value=Mock(returncode=0)
    ) as run:
        result = probe_acceleration("ffmpeg", "cuda")
    assert result["effective"] == "cuda"
    assert result["status"] == "verified"
    command = run.call_args.args[0]
    assert command[command.index("-i") + 1] == "color=c=black:s=128x128:r=1"
    assert command[command.index("-frames:v") + 1] == "1"
    assert run.call_args.kwargs["timeout"] == 8


@pytest.mark.parametrize(
    "failure", [None, OSError(), subprocess.TimeoutExpired("ffmpeg", 8)]
)
def test_failed_cuda_initialization_falls_back_to_software(failure):
    with patch(
        "app.runtime_health.subprocess.run",
        return_value=Mock(returncode=1),
        side_effect=failure,
    ):
        result = probe_acceleration("ffmpeg", "cuda")
    assert result["effective"] == "false"
    assert result["status"] == "failed"


def test_disabled_acceleration_never_launches_ffmpeg():
    with patch("app.runtime_health.subprocess.run") as run:
        assert probe_acceleration("ffmpeg", "false")["status"] == "disabled"
    run.assert_not_called()
