from __future__ import annotations

from pathlib import Path

from PIL import Image

from scripts import eufy_mac_grid_exporter


def test_parse_roi_supports_normalized_values() -> None:
    assert eufy_mac_grid_exporter.parse_roi("0.25,0.25,0.5,0.5", (200, 100)) == (
        50,
        25,
        150,
        75,
    )


def test_parse_roi_supports_pixel_values() -> None:
    assert eufy_mac_grid_exporter.parse_roi("10,20,30,40", (200, 100)) == (
        10,
        20,
        40,
        60,
    )


def test_export_device_crops_writes_named_pngs(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    image = Image.new("RGB", (100, 100), (0, 0, 0))
    for x in range(0, 50):
        for y in range(0, 50):
            image.putpixel((x, y), (255, 0, 0))
    for x in range(50, 100):
        for y in range(0, 50):
            image.putpixel((x, y), (0, 255, 0))
    image.save(source, format="PNG")

    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    written = eufy_mac_grid_exporter.export_device_crops(
        source,
        [
            {
                "name": "Left",
                "snapshot_path": str(left),
                "roi": "0,0,50,50",
            },
            {
                "name": "Right",
                "snapshot_path": str(right),
                "roi": "0.5,0,0.5,0.5",
            },
        ],
    )

    assert written == 2
    with Image.open(left) as left_image:
        assert left_image.size == (50, 50)
        assert left_image.getpixel((10, 10)) == (255, 0, 0)
    with Image.open(right) as right_image:
        assert right_image.size == (50, 50)
        assert right_image.getpixel((10, 10)) == (0, 255, 0)
