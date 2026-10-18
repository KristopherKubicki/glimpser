"""Near-black sensor noise must not be presented as recovered detail."""

import numpy as np

from scripts.media_enhancement.illumination import recover_lighting


def test_black_frame_with_small_overlay_is_held():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:2, :20] = 255
    result, info = recover_lighting(frame)
    np.testing.assert_array_equal(result, frame)
    assert info["state"] == "held"
    assert info["reason"] == "insufficient_signal"
