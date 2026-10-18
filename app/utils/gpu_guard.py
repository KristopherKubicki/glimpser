"""Compatibility alias for gpu_guard."""

import sys

from app import gpu_guard as _implementation

sys.modules[__name__] = _implementation
