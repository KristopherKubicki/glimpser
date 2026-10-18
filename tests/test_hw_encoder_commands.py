from pathlib import Path
from unittest.mock import patch

from app import routes
from app.utils import video_archiver


@patch("app.config.FFMPEG_HWACCEL", "cuda")
def test_live_encoding_stays_software_with_cuda_decode():
    command = routes.build_live_ffmpeg_command(
        "rtsp://camera.example/stream",
        width=1280,
        fps=5,
        transcode_rtsp=True,
    )

    assert "libx264" in command
    assert "h264_nvenc" not in command
    assert "-tune" in command
    assert "zerolatency" in command


@patch("app.utils.video_archiver.FFMPEG_HWACCEL", "cuda")
@patch("app.utils.video_archiver.run_ffmpeg")
def test_reencode_concat_uses_encoder_helper(mock_run_ffmpeg, tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"input")

    video_archiver._reencode_concat(str(input_path), str(output_path))

    command = mock_run_ffmpeg.call_args.args[0]
    assert "libx264" in command
    assert "h264_nvenc" not in command
    assert "veryfast" in command
