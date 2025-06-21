import pytest
import app.config as config
from app.utils.cli import parse_arguments


def test_parse_arguments_defaults():
    args = parse_arguments([])
    assert args.db_path == config.DATABASE_PATH
    assert args.host == config.HOST
    assert args.port == config.PORT
    assert args.log_path == config.LOGGING_PATH
    assert args.log_level == config.LOG_LEVEL
    assert args.console_log is False
    assert args.debug == config.DEBUG
    assert args.no_scheduler is False
    assert args.no_watchdog is False
    assert args.no_crawlers is False
    assert args.no_log_cache is False
    assert args.screenshot_dir == config.SCREENSHOT_DIRECTORY
    assert args.video_dir == config.VIDEO_DIRECTORY
    assert args.summaries_dir == config.SUMMARIES_DIRECTORY


def test_parse_arguments_flags():
    args = parse_arguments(
        [
            "--port",
            "1234",
            "--console-log",
            "--debug",
            "--no-scheduler",
        ]
    )
    assert args.port == 1234
    assert args.console_log is True
    assert args.debug is True
    assert args.no_scheduler is True


def test_parse_arguments_invalid_port():
    with pytest.raises(SystemExit):
        parse_arguments(["--port", "not_a_number"])
