from PIL import Image

from app.utils.satellite_map import generate_satellite_map, save_satellite_map

LINE1 = "1 25544U 98067A   20350.54791667  .00001282  00000-0  29646-4 0  9992"
LINE2 = "2 25544  51.6443 165.4227 0002294 264.5031  95.5168 15.49154726    00"


def test_generate_satellite_map():
    img = generate_satellite_map(LINE1, LINE2, width=360, height=180, minutes=2)
    assert isinstance(img, Image.Image)
    assert img.size == (360, 180)
    assert any(px != (0, 0, 0) for px in img.getdata())


def test_save_satellite_map(tmp_path):
    path = tmp_path / "map.png"
    save_satellite_map(str(path), LINE1, LINE2, width=120, height=60, minutes=1)
    assert path.exists()
    with Image.open(path) as im:
        assert im.size == (120, 60)
