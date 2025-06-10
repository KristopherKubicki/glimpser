"""CLI helper utilities."""

from __future__ import annotations

import argparse

import app.config as config


def build_argument_parser() -> argparse.ArgumentParser:
    """Return the ``argparse`` parser used for the ``glimpser`` CLI."""
    parser = argparse.ArgumentParser(description=f"Glimpser {config.VERSION}")
    parser.add_argument(
        "--db-path",
        default=config.DATABASE_PATH,
        help=f"Path to the database file (default: {config.DATABASE_PATH})",
    )
    parser.add_argument(
        "--host",
        default=config.HOST,
        help=f"Host for the web server (default: {config.HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.PORT,
        help=f"Port for the web server (default: {config.PORT})",
    )
    parser.add_argument(
        "--log-path",
        default=config.LOGGING_PATH,
        help=f"Path to the log file (default: {config.LOGGING_PATH})",
    )
    parser.add_argument(
        "--log-level",
        default=config.LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    parser.add_argument(
        "--console-log",
        action="store_true",
        help="Enable logging to the console",
        default=False,
    )
    parser.add_argument("--debug", action="store_true", default=config.DEBUG, help="Enable debug mode")
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="Disable the background scheduler",
        default=False,
    )
    parser.add_argument(
        "--no-watchdog",
        action="store_true",
        help="Disable the watchdog thread",
        default=False,
    )
    parser.add_argument(
        "--no-crawlers",
        action="store_true",
        help="Skip scheduling crawler jobs",
        default=False,
    )
    parser.add_argument(
        "--no-log-cache",
        action="store_true",
        help="Disable the log caching thread",
        default=False,
    )
    parser.add_argument(
        "--screenshot-dir",
        default=config.SCREENSHOT_DIRECTORY,
        help="Directory for storing screenshots",
    )
    parser.add_argument(
        "--video-dir",
        default=config.VIDEO_DIRECTORY,
        help="Directory for storing video files",
    )
    parser.add_argument(
        "--summaries-dir",
        default=config.SUMMARIES_DIRECTORY,
        help="Directory for storing summaries",
    )
    return parser


def parse_arguments(arg_list: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments and return the populated ``Namespace``."""
    parser = build_argument_parser()
    return parser.parse_args(arg_list)


def cli_help_text() -> str:
    """Return the formatted ``--help`` text for the CLI."""
    parser = build_argument_parser()
    return parser.format_help()
