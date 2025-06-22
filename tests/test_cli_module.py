from unittest.mock import patch

import pytest

from app.utils import cli


def _patch_defaults():
    return patch.multiple(
        cli.config,
        DATABASE_PATH="db.sqlite",
        HOST="0.0.0.0",
        PORT=9999,
        LOGGING_PATH="app.log",
        LOG_LEVEL="INFO",
        DEBUG=False,
        SCREENSHOT_DIRECTORY="shots",
        VIDEO_DIRECTORY="videos",
        SUMMARIES_DIRECTORY="summs",
        VERSION="0.0",
    )


def test_parse_arguments_defaults():
    with _patch_defaults():
        args = cli.parse_arguments([])
        assert args.db_path == "db.sqlite"
        assert args.host == "0.0.0.0"
        assert args.port == 9999
        assert args.log_path == "app.log"
        assert args.log_level == "INFO"
        assert args.debug is False
        assert args.screenshot_dir == "shots"
        assert args.video_dir == "videos"
        assert args.summaries_dir == "summs"


def test_parse_arguments_custom_values():
    with _patch_defaults():
        args = cli.parse_arguments(
            ["--db-path", "custom.db", "--port", "1234", "--debug"]
        )
        assert args.db_path == "custom.db"
        assert args.port == 1234
        assert args.debug is True


def test_cli_help_text_contains_options():
    with _patch_defaults():
        text = cli.cli_help_text()
    assert "--db-path" in text
    assert "Glimpser 0.0" in text


def test_version_argument_outputs_version(capsys):
    with _patch_defaults():
        parser = cli.build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])
    captured = capsys.readouterr()
    assert "0.0" in captured.out
