"""Helper utilities used across Glimpser.

This package collects modules for network checks, camera interaction,
scheduling tasks, alerting, and other supporting functionality.
"""

from importlib import import_module

from .throttle import clear as clear_throttle
from .throttle import limit_rate as limit_rate

__all__ = ["console_dashboard", "clear_throttle", "limit_rate"]


def __getattr__(name: str):
    """Load the optional terminal dashboard only when explicitly requested."""
    if name == "console_dashboard":
        module = import_module(".console_dashboard", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
