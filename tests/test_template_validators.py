import pytest

from app.utils.template_manager import Template, is_snapshot_url


def test_is_snapshot_url_true_cases():
    assert is_snapshot_url("http://example.com/image.jpg")
    assert is_snapshot_url("http://example.com/path/snapshot")
    assert is_snapshot_url("http://example.com/foo/picture")


def test_is_snapshot_url_false_cases():
    assert not is_snapshot_url("http://example.com/video.mp4")
    assert not is_snapshot_url("")


def test_validate_frequency_limit():
    t = Template(frequency=60)
    with pytest.raises(ValueError):
        t.validate_frequency("frequency", 525601)
    assert t.validate_frequency("frequency", 100) == 100


def test_validate_timeout_negative_and_excess():
    t = Template(frequency=60)
    assert t.validate_timeout("timeout", -5) == 10
    with pytest.raises(ValueError):
        t.validate_timeout("timeout", t.frequency * 60)


def test_validate_xpath():
    t = Template()
    assert t.validate_xpath("popup_xpath", "//div") == "//div"
    with pytest.raises(ValueError):
        t.validate_xpath("popup_xpath", "div")


def test_validate_object_confidence():
    t = Template(object_filter="dog")
    with pytest.raises(ValueError):
        t.validate_object_confidence("object_confidence", 1.5)
    t_no_filter = Template(object_filter="")
    assert t_no_filter.validate_object_confidence("object_confidence", 1.5) == 1.5
