from app.utils import camera_discovery, screenshots
from app.utils.validators import url_matches_host


def test_host_matching_does_not_trust_paths_or_userinfo():
    assert url_matches_host("https://www.youtube.com/watch?v=x", "youtube.com")
    for url in (
        "https://youtube.com.evil.example/",
        "https://evil.example/youtube.com",
        "https://youtube.com@evil.example/",
        "https://[",
    ):
        assert not url_matches_host(url, "youtube.com")


def test_camera_xml_rejects_entity_expansion():
    payload = b"""<!DOCTYPE r [<!ENTITY value "EXPANDED">]>
        <r><Profiles token="one"><Name>&value;</Name></Profiles></r>"""
    assert camera_discovery._onvif_parse_profiles(payload) == []


def test_url_credentials_are_decoded_without_regex_backtracking():
    for auth in (screenshots.get_auth, screenshots.get_digest_auth):
        credentials = auth("http://user%40home:p%3Ass@example.com")
        assert credentials.username == "user@home"
        assert credentials.password == "p:ss"  # pragma: allowlist secret
        assert auth("https://example.com/" + "/9" * 10000) is None


def test_browser_redirect_rejects_network_paths_and_controls():
    from app.routes import is_safe_redirect_url

    for target in (
        "///evil.example",
        "/\\evil.example",
        "\x00//evil.example",
        "https://[",
    ):
        assert not is_safe_redirect_url(target)
    assert is_safe_redirect_url("/templates/camera")


def test_web_routes_reject_arbitrary_shortcuts_and_preview_files(tmp_path):
    from unittest.mock import patch

    from flask import Flask

    from app.routes import init_routes

    with patch("app.routes.login_required", lambda view: view):
        app = Flask(__name__)
        init_routes(app)
    client = app.test_client()
    with patch("app.routes.update_chrome_shortcuts_info") as update:
        response = client.post(
            "/danger",
            data={
                "action": "update_shortcut",
                "shortcut_path": str(tmp_path / "private"),
            },
        )
        assert response.status_code == 400
        update.assert_not_called()
    response = client.get("/recovery/preview/private.json")
    assert response.status_code == 404
