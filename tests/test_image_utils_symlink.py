import os
import tempfile
import unittest.mock

from PIL import Image

from app.utils.image_utils import add_motion_and_caption


def test_symlink_target_is_updated_without_replacing_link():
    with unittest.mock.patch("app.utils.scheduling.DEBUG", False):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target.png")
            link = os.path.join(tmp, "link.png")
            Image.new("RGB", (50, 50), color="white").save(target)
            os.symlink(target, link)

            original_target = open(target, "rb").read()
            add_motion_and_caption(link, caption="hi", motion=True)
            updated_target = open(target, "rb").read()

            assert os.path.islink(link)
            assert original_target != updated_target
            Image.open(target).verify()
