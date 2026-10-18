"""Colorization preparation must preserve source evidence and reject bad input."""

import numpy as np
import pytest

from scripts.media_enhancement.colorize import grayscale_metrics, prepare_inference


def test_float_input_is_rejected():
    with pytest.raises(ValueError, match="geometry"):
        grayscale_metrics(np.zeros((8, 8, 3), dtype=float))


def test_shadow_lift_does_not_mutate_evidence():
    source = np.full((8, 8, 3), 60, dtype=np.uint8)
    source[0, 0] = 255
    before = source.copy()
    result, gain = prepare_inference(source)
    np.testing.assert_array_equal(source, before)
    np.testing.assert_array_equal(result[0, 0], source[0, 0])
    assert 1 <= gain <= 2
    assert result[1, 1, 0] > source[1, 1, 0]
