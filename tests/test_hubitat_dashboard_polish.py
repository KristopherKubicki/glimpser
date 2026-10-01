from app.utils.screenshots import _browser_capture_profile


def test_local_hubitat_v2_gets_full_dashboard_capture_profile(monkeypatch):
    from app import capture_policy

    monkeypatch.setattr(
        capture_policy, "CAPTURE_POLICY", {"hubitat_hosts": ["hub.example"]}
    )
    profile = _browser_capture_profile(
        "http://hub.example/dashboard/ui/950", "HubitatInteriorMotion"
    )
    assert profile["hubitat_cloud_dashboard"] is True
    assert profile["viewport"] == (1920, 1080)


def test_unrelated_dashboard_ui_is_not_restyled_as_hubitat():
    profile = _browser_capture_profile("https://example.com/dashboard/ui/950", "Other")
    assert profile["hubitat_cloud_dashboard"] is False


def test_dashboard_with_no_loaded_camera_images_is_not_published(monkeypatch):
    import pytest

    from app.utils import screenshots

    monkeypatch.setattr(
        screenshots,
        "_apply_hubitat_cloud_dashboard_visual_cleanup",
        lambda *args: {"images": 4, "statuses": 5},
    )

    class Driver:
        def execute_script(self, script):
            return "every(" in script

    with pytest.raises(
        screenshots.TimeoutException, match="camera images were unavailable"
    ):
        screenshots._settle_hubitat_dashboard_for_capture(Driver(), "HubitatTest")


def test_private_labels_are_passed_as_data_and_filtered_to_inventory(monkeypatch):
    from unittest.mock import Mock

    from app import capture_policy
    from app.utils import screenshots, template_manager

    monkeypatch.setattr(
        capture_policy,
        "CAPTURE_POLICY",
        {
            "dashboard_camera_labels": {
                "ExampleDoor": "</script>Entrance",
                "Absent": "Private label",
            }
        },
    )
    monkeypatch.setattr(template_manager, "get_templates", lambda: {"ExampleDoor": {}})
    driver = Mock()
    driver.execute_script.return_value = {"images": 1}
    screenshots._apply_hubitat_cloud_dashboard_visual_cleanup(driver, "HubitatExample")
    args = driver.execute_script.call_args.args
    assert args[3] == {"ExampleDoor": "</script>Entrance"}
    assert "</script>Entrance" not in args[0]
