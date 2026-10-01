import io
from datetime import datetime
from unittest.mock import patch

import pytest
from PIL import Image

from app import routes


@pytest.fixture(autouse=True)
def clear_cache():
    routes._render_stream_timestamp.cache_clear()
    yield
    routes._render_stream_timestamp.cache_clear()


def jpeg(color):
    output = io.BytesIO()
    Image.new("RGB", (1280, 720), color).save(output, format="JPEG")
    return output.getvalue()


def test_viewers_share_encoding_but_new_seconds_and_images_do_not():
    red, blue = jpeg("red"), jpeg("blue")
    render = routes._render_stream_timestamp
    with patch.object(routes, "datetime") as clock:
        clock.now.return_value = datetime(2026, 9, 29, 12, 0, 0)
        first = routes._overlay_stream_timestamp(red)
        assert all(routes._overlay_stream_timestamp(red) == first for _ in range(7))
        assert render.cache_info().misses == 1
        assert first == render.__wrapped__(red, "12:00:00")
        changed = routes._overlay_stream_timestamp(blue)
        with Image.open(io.BytesIO(changed)) as image:
            assert image.getpixel((0, 0))[2] > 240
        clock.now.return_value = datetime(2026, 9, 29, 12, 0, 1)
        assert routes._overlay_stream_timestamp(red) != first
        assert render.cache_info().misses == 3


def test_cache_is_bounded_and_oversized_sources_bypass_it():
    source = jpeg("red")
    render = routes._render_stream_timestamp
    for second in range(20):
        render(source, f"12:00:{second:02d}")
    assert render.cache_info().currsize == 8
    oversized = source + b"\0" * (256 * 1024)
    before = render.cache_info()
    assert routes._overlay_stream_timestamp(oversized) != oversized
    assert render.cache_info() == before


def test_bad_input_falls_back_without_caching_failure():
    assert routes._overlay_stream_timestamp(b"not a jpeg") == b"not a jpeg"
    assert routes._render_stream_timestamp.cache_info().currsize == 0
