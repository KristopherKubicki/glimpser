"""Compatibility alias for encoder_pipe."""

import sys

from app import encoder_pipe as _implementation

sys.modules[__name__] = _implementation
