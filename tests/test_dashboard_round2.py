from PIL import Image, ImageFile

from app.utils.screenshots import _is_valid_png


def test_partial_png_is_rejected_even_with_tolerant_pillow(tmp_path, monkeypatch):
    path = tmp_path / "partial.png"
    Image.new("RGB", (100, 100), "red").save(path)
    assert _is_valid_png(str(path))
    path.write_bytes(path.read_bytes()[:-30])
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", True)
    assert not _is_valid_png(str(path))
