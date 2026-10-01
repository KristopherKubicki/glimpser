from pathlib import Path

from PIL import Image, ImageDraw

from app.utils.screenshots import (
    _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT,
    _captured_frame_rejection_reason,
    _finalize_screenshot,
    is_sparse_dashboard_frame,
)


def _sparse_hubitat_dashboard_frame(path: Path) -> None:
    image = Image.new("RGB", (1600, 1200), (18, 28, 40))
    draw = ImageDraw.Draw(image)
    for x in range(20, 800, 160):
        draw.rounded_rectangle(
            (x, 20, x + 120, 140),
            fill=(24, 37, 54),
            outline=(90, 110, 130),
            radius=8,
        )
        draw.rectangle((x + 45, 45, x + 75, 75), fill=(180, 255, 140))
    image.save(path)


def _hubitat_loader_frame(path: Path) -> None:
    image = Image.new("RGB", (1600, 1200), (17, 25, 38))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 470, 505, 485), fill=(150, 150, 150), radius=6)
    image.save(path)


def test_sparse_hubitat_dashboard_frame_requires_trusted_bypass(tmp_path):
    source = tmp_path / "source.png"
    normal_output = tmp_path / "normal.png"
    trusted_output = tmp_path / "trusted.png"
    _sparse_hubitat_dashboard_frame(source)

    with Image.open(source) as image:
        assert _captured_frame_rejection_reason(image) == "loading"
        assert is_sparse_dashboard_frame(image)

    normal_tmp = tmp_path / "normal.tmp.png"
    normal_tmp.write_bytes(source.read_bytes())
    assert (
        _finalize_screenshot(
            str(normal_tmp),
            str(normal_output),
            "HubitatExampleOfficeStatus",
            False,
            False,
        )
        is False
    )

    trusted_tmp = tmp_path / "trusted.tmp.png"
    trusted_tmp.write_bytes(source.read_bytes())
    assert (
        _finalize_screenshot(
            str(trusted_tmp),
            str(trusted_output),
            "HubitatExampleOfficeStatus",
            False,
            False,
            allow_sparse_capture=True,
        )
        is True
    )
    assert trusted_output.exists()


def test_hubitat_loader_bar_is_not_trusted_sparse_dashboard(tmp_path):
    source = tmp_path / "loader.png"
    output = tmp_path / "loader-output.png"
    _hubitat_loader_frame(source)

    with Image.open(source) as image:
        assert _captured_frame_rejection_reason(image) in {"blank", "loading"}
        assert not is_sparse_dashboard_frame(image)

    tmp = tmp_path / "loader.tmp.png"
    tmp.write_bytes(source.read_bytes())
    assert (
        _finalize_screenshot(
            str(tmp),
            str(output),
            "HubitatControlPanel",
            False,
            False,
            allow_sparse_capture=True,
        )
        is False
    )


def test_bright_hubitat_error_page_is_not_trusted_sparse_dashboard(tmp_path):
    source = tmp_path / "hubitat-error.png"
    output = tmp_path / "hubitat-error-output.png"
    image = Image.new("RGB", (1600, 1200), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((650, 420), "No response from hub", fill=(80, 80, 80))
    image.save(source)

    with Image.open(source) as image:
        assert _captured_frame_rejection_reason(image) == "blank"
        assert not is_sparse_dashboard_frame(image)

    tmp = tmp_path / "hubitat-error.tmp.png"
    tmp.write_bytes(source.read_bytes())
    assert (
        _finalize_screenshot(
            str(tmp),
            str(output),
            "HubitatBeachMain",
            False,
            False,
            url="https://cloud.hubitat.com/api/example/apps/17/ui",
            allow_sparse_capture=True,
        )
        is False
    )


def test_hubitat_dashboard_cleanup_detects_legacy_image_sources():
    assert "embedded_screenshot" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "backgroundImage" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "latest_camera" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT


def test_hubitat_dashboard_cleanup_packs_status_only_dashboards():
    assert "eyebat-hubitat-status-stage" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "buildCompactStatusCard" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "buildStatusOnlyCard" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "statusOnly" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "seenStatusKeys" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "visualClockOnly" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT.find(
        "hideMaterialIconTextChrome();"
    ) > _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT.find("const materialIconLiterals")
    assert '[data-tour^="DashboardItem_"]' in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert '[data-testid^="DashboardItem_"]' in (_HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT)
    assert ".react-grid-item" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert ".grid-stack-item" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert ".dashboard-tile" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "replace(/^\\.+/" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "skip_next|skip_previous|volume_up" in (
        _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    )
    assert "^Dashboards\\s+(.+)$" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "^Receiver\\s+(.+)$" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "hideMaterialIconTextChrome" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "smallFloatingControl" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "nearViewportEdge" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "overflow-wrap', 'anywhere'" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "'-webkit-line-clamp', height < 100 ? '1' : '2'" in (
        _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    )
    assert "function rowBox" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "const statusBudget" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "more_horiz" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "height', '100%'" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "overflow', 'hidden'" in _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    assert "if (isLegacyDashboard) {\n        item.style.setProperty('display'" not in (
        _HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT
    )


def test_hubitat_named_dashboard_suppresses_name_overlay(tmp_path):
    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    image = Image.new("RGB", (800, 450), (20, 30, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 100, 600, 350), fill=(50, 140, 180))
    image.save(source)

    assert _finalize_screenshot(
        str(source),
        str(output),
        "HubitatLocalDashboard",
        False,
        False,
        url="http://192.168.50.129/apps/api/193/dashboard/426",
    )

    with Image.open(output) as result:
        assert result.getpixel((5, 5)) == (20, 30, 40)
