import hashlib
import os
import shutil
import tempfile
import time
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image, ImageDraw

import app.utils.screenshots as ss


class TestScreenshotsExtras(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.patcher = patch(
            "app.utils.screenshots.STATUS_CACHE_PATH",
            os.path.join(self.tmpdir, "cache.json"),
        )
        self.patcher.start()
        ss.status_code_cache.clear()
        ss.status_code_cache_time.clear()
        ss.last_modified_cache.clear()
        ss.etag_cache.clear()
        ss.etag_flip_cache.clear()
        ss.image_hash_cache.clear()
        ss.image_hash_cache_time.clear()
        ss._persist_status_cache()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_is_valid_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            Image.new("RGB", (1, 1)).save(tmp, format="PNG")
            tmp_path = tmp.name
        try:
            self.assertTrue(ss._is_valid_png(tmp_path))
            with open(tmp_path, "wb") as f:
                f.write(b"not a png")
            self.assertFalse(ss._is_valid_png(tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_cached_status_code(self):
        url = "http://example.com"
        ss.set_cached_status_code(url, 201)
        self.assertEqual(ss.get_cached_status_code(url), 201)
        ss.status_code_cache_time[url] -= ss.STATUS_CACHE_TTL + 1
        self.assertIsNone(ss.get_cached_status_code(url))

    def test_check_if_modified(self):
        url = "http://example.com"
        headers = {"Last-Modified": "Mon, 01 Jan 2020 00:00:00 GMT", "ETag": "abc"}
        self.assertTrue(ss.check_if_modified(url, headers))
        self.assertFalse(ss.check_if_modified(url, headers))

    def test_auth_helpers(self):
        url = "http://user:pass@example.com"  # pragma: allowlist secret
        basic = ss.get_auth(url)
        digest = ss.get_digest_auth(url)
        self.assertEqual(basic.username, "user")
        self.assertEqual(basic.password, "pass")
        self.assertEqual(digest.username, "user")
        self.assertEqual(digest.password, "pass")
        fallback = ss.get_auth("http://example.com", "u", "p")
        self.assertEqual(fallback.username, "u")
        self.assertEqual(fallback.password, "p")

    def test_url_type_helpers(self):
        self.assertTrue(ss.is_image_url("http://x/a.jpg", ""))
        self.assertTrue(ss.is_pdf_url("http://x/doc.pdf", ""))
        self.assertTrue(ss.is_video_stream_url("rtsp://cam", ""))
        self.assertFalse(ss.is_video_stream_url("http://x/image.png", "image/png"))

    def test_browser_selection(self):
        url = "http://example.com"
        with patch.object(ss, "is_enhanced", return_value=False):
            self.assertTrue(
                ss.should_use_lightweight_browser(
                    url, None, None, False, False, False, False
                )
            )
            self.assertFalse(
                ss.should_use_lightweight_browser(
                    url, None, None, True, False, False, False
                )
            )
            self.assertTrue(
                ss.should_use_phantom_browser(
                    url, None, None, False, False, False, False
                )
            )
            self.assertFalse(
                ss.should_use_phantom_browser(
                    url, None, None, False, True, False, False
                )
            )

    def test_browser_capture_profile_detects_flight_tracker(self):
        profile = ss._browser_capture_profile(
            "https://www.flightradar24.com/", "FlightRadar"
        )

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(
            profile["auto_dedicated_xpath"], "//*[@id='app']//main | //main"
        )
        self.assertEqual(profile["page_load_strategy"], "eager")
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertIn(
            "[data-testid='most-tracked-flights-widget']",
            tuple(profile["hide_selectors"]),
        )
        self.assertIn(
            "[data-testid='sidebar__container']", tuple(profile["hide_selectors"])
        )
        self.assertGreater(float(profile["post_load_delay"]), 0.0)
        self.assertEqual(tuple(profile["viewport"]), (2560, 1440))

    def test_browser_capture_profile_uses_map_crop_for_flightaware(self):
        profile = ss._browser_capture_profile(
            "https://www.flightaware.com/live/", "FAA"
        )

        self.assertEqual(profile["auto_dedicated_xpath"], "//*[@id='map'] | //main")
        self.assertIn("#onetrust-consent-sdk", tuple(profile["hide_selectors"]))
        self.assertIn("//*[@id='onetrust-consent-sdk']", tuple(profile["popup_xpaths"]))

    def test_browser_capture_profile_detects_earthcam(self):
        profile = ss._browser_capture_profile(
            "https://www.earthcam.com/usa/illinois/chicago/midwayairport/?cam=midwayairport",
            "Midway",
        )

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(
            profile["auto_dedicated_xpath"], "//*[@id='ecnPlayer'] | //main"
        )
        self.assertIn(".selectorArea", tuple(profile["hide_selectors"]))
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_browser_capture_profile_detects_boatnerd_ais(self):
        profile = ss._browser_capture_profile(
            "https://ais.boatnerd.com/",
            "BoatnerdAISGreatLakes",
        )

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(profile["page_load_strategy"], "eager")
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertEqual(profile["auto_dedicated_xpath"], "")
        self.assertIn(
            "//button[normalize-space()='Skip']", tuple(profile["click_xpaths"])
        )
        self.assertIn(
            "//*[contains(normalize-space(.),'Welcome to BoatNerd')]",
            tuple(profile["popup_xpaths"]),
        )
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))
        self.assertGreaterEqual(int(profile["timeout_floor"]), 45)

    def test_browser_capture_profile_detects_skyline_webcams_player(self):
        profile = ss._browser_capture_profile(
            "https://www.skylinewebcams.com/en/webcam/united-states/michigan/sault-ste-marie/soo-locks.html",
            "SkylineSooLocks",
        )

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(profile["page_load_strategy"], "eager")
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertEqual(
            profile["auto_dedicated_xpath"],
            "//*[@id='skylinewebcams'] | //*[@id='webcam'] | //iframe[contains(@src,'youtube')]",
        )
        self.assertIn(".adsbygoogle", tuple(profile["hide_selectors"]))
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))
        self.assertGreaterEqual(int(profile["timeout_floor"]), 45)

    def test_browser_capture_profile_detects_electricity_maps(self):
        profile = ss._browser_capture_profile(
            "https://app.electricitymaps.com/map", "Energy"
        )

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(profile["page_load_strategy"], "eager")
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertEqual(
            profile["auto_dedicated_xpath"],
            "//canvas[contains(@class,'maplibregl-canvas')] | //main",
        )
        self.assertEqual(tuple(profile["viewport"]), (1920, 1200))
        self.assertTrue(profile["force_dark_visual_filter"])

    def test_browser_capture_profile_detects_kubra_stormcenter(self):
        profile = ss._browser_capture_profile(
            "https://kubra.io/stormcenter/views/abc123", "ComEd"
        )

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(profile["page_load_strategy"], "eager")
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertEqual(profile["auto_dedicated_xpath"], "//main | //body")
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))
        self.assertTrue(profile["force_dark_visual_filter"])

    def test_browser_capture_profile_detects_gpsjam(self):
        profile = ss._browser_capture_profile("https://gpsjam.org/", "GPSJam")

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(profile["page_load_strategy"], "eager")
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertEqual(profile["auto_dedicated_xpath"], "")
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))
        self.assertGreaterEqual(int(profile["timeout_floor"]), 45)

    def test_browser_capture_profile_detects_storefront_overlay_cleanup(self):
        profile = ss._browser_capture_profile("https://abt.com", "Abt.com")

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(profile["page_load_strategy"], "eager")
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertEqual(profile["auto_dedicated_xpath"], "")
        self.assertIn("[role='dialog']", tuple(profile["hide_selectors"]))
        self.assertIn(
            "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newsletter')]",
            tuple(profile["popup_xpaths"]),
        )
        self.assertIn("[id*='klaviyo' i]", tuple(profile["hide_selectors"]))
        self.assertIn("[class*='privy' i]", tuple(profile["hide_selectors"]))
        self.assertIn("[id*='account' i]", tuple(profile["hide_selectors"]))
        self.assertIn("[class*='flyout' i]", tuple(profile["hide_selectors"]))
        self.assertIn(
            "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'log in for the best experience')]",
            tuple(profile["popup_xpaths"]),
        )
        self.assertIn(
            "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'dropdown')]",
            tuple(profile["popup_xpaths"]),
        )
        self.assertIn(
            "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email-capture')]",
            tuple(profile["popup_xpaths"]),
        )
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))
        self.assertGreaterEqual(int(profile["timeout_floor"]), 45)

    def test_browser_capture_profile_detects_youtube_streams_wall(self):
        profile = ss._browser_capture_profile(
            "https://www.youtube.com/@ohareplanespotting/streams",
            "OharePlanespottingStreams",
        )

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertTrue(profile["force_dark_visual_filter"])
        self.assertTrue(profile["preserve_visual_media_on_dark_filter"])
        self.assertIn("ytd-rich-grid-renderer", profile["auto_dedicated_xpath"])
        self.assertIn("ytd-masthead", tuple(profile["hide_selectors"]))
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_browser_capture_profile_detects_news_dark_fallback(self):
        profile = ss._browser_capture_profile("https://apnews.com/", "APNews")

        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertTrue(profile["continue_after_load_timeout"])
        self.assertTrue(profile["force_dark_visual_filter"])
        self.assertTrue(profile["preserve_visual_media_on_dark_filter"])
        self.assertIn("//main", profile["auto_dedicated_xpath"])
        self.assertIn("[id*='newsletter' i]", tuple(profile["hide_selectors"]))
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_browser_capture_profile_detects_browser_diagnostics_dark_fallback(self):
        for url, name in (
            ("https://browserleaks.com/", "BrowserLeaks"),
            ("https://abrahamjuliot.github.io/creepjs/", "CreepJS"),
            ("https://bot.sannysoft.com/", "Antibot"),
        ):
            with self.subTest(name=name):
                profile = ss._browser_capture_profile(url, name)

                self.assertTrue(profile["prefer_rich_graphics"])
                self.assertTrue(profile["continue_after_load_timeout"])
                self.assertTrue(profile["force_dark_visual_filter"])
                self.assertEqual(profile["dark_visual_filter_mode"], "theme")
                self.assertFalse(profile["preserve_visual_media_on_dark_filter"])
                self.assertEqual(profile["auto_dedicated_xpath"], "//main | //body")
                self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_browser_capture_profile_detects_status_dark_fallback(self):
        status_profile = ss._browser_capture_profile(
            "https://www.deeplisten.tv/status",
            "DeepListen",
        )

        self.assertTrue(status_profile["force_dark_visual_filter"])
        self.assertEqual(status_profile["dark_visual_filter_mode"], "theme")
        self.assertFalse(status_profile["preserve_visual_media_on_dark_filter"])
        self.assertEqual(status_profile["auto_dedicated_xpath"], "//main | //body")

    def test_browser_capture_profile_detects_public_data_dashboard_dark_fallback(self):
        for url, name in (
            ("https://waterwatch.usgs.gov/", "Stream"),
            ("https://charts.ecmwf.int/", "ECMWF"),
            ("https://www.glerl.noaa.gov/data/ice/", "IceCover"),
        ):
            with self.subTest(name=name):
                profile = ss._browser_capture_profile(url, name)

                self.assertTrue(profile["prefer_rich_graphics"])
                self.assertTrue(profile["continue_after_load_timeout"])
                self.assertTrue(profile["force_dark_visual_filter"])
                self.assertFalse(profile["preserve_visual_media_on_dark_filter"])
                self.assertIn("//article", profile["auto_dedicated_xpath"])
                self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_browser_capture_profile_detects_listing_shop_dark_fallback(self):
        for url, name in (
            ("https://www.redfin.com/", "Redfin"),
            ("https://costco.com/", "Costco"),
        ):
            with self.subTest(name=name):
                profile = ss._browser_capture_profile(url, name)

                self.assertTrue(profile["prefer_rich_graphics"])
                self.assertTrue(profile["continue_after_load_timeout"])
                self.assertTrue(profile["force_dark_visual_filter"])
                self.assertEqual(profile["dark_visual_filter_mode"], "theme")
                self.assertTrue(profile["preserve_visual_media_on_dark_filter"])
                self.assertEqual(profile["auto_dedicated_xpath"], "//main | //body")

    def test_browser_capture_profile_detects_network_dark_fallback(self):
        fast_profile = ss._browser_capture_profile("https://fast.com/", "Fast.com")
        modem_profile = ss._browser_capture_profile(
            "http://172.16.0.1/xslt?PAGE=C_2_0", "Modem"
        )

        self.assertTrue(fast_profile["force_dark_visual_filter"])
        self.assertTrue(fast_profile["prefer_rich_graphics"])
        self.assertFalse(fast_profile["allow_private_network_images"])
        self.assertEqual(fast_profile["dark_visual_filter_mode"], "theme")
        self.assertEqual(fast_profile["auto_dedicated_xpath"], "//body")

        self.assertTrue(modem_profile["force_dark_visual_filter"])
        self.assertTrue(modem_profile["prefer_rich_graphics"])
        self.assertTrue(modem_profile["allow_private_network_images"])
        self.assertEqual(modem_profile["dark_visual_filter_mode"], "theme")
        self.assertIn("//*[@id='contents']", modem_profile["auto_dedicated_xpath"])

    def test_browser_capture_profile_detects_dynamic_weather_maps(self):
        for url, name in (
            ("https://www.windy.com/?42.034,-87.757,5", "Wind"),
            ("https://map.blitzortung.org/#4.72/42.06/-87.41", "Lightning2"),
        ):
            profile = ss._browser_capture_profile(url, name)

            self.assertTrue(profile["prefer_rich_graphics"])
            self.assertEqual(profile["page_load_strategy"], "eager")
            self.assertTrue(profile["continue_after_load_timeout"])
            self.assertEqual(tuple(profile["viewport"]), (1920, 1080))
            self.assertGreaterEqual(int(profile["timeout_floor"]), 60)
            self.assertGreaterEqual(float(profile["post_load_delay"]), 15.0)

    def test_uid_cgi_snapshot_url_uses_dynamic_uid(self):
        response = MagicMock()
        response.ok = True
        response.text = '<?xml version="1.0"?><uid>ABC123</uid>'
        session = MagicMock()
        session.get.return_value = response

        with patch.object(ss, "http_session", return_value=session):
            snapshot_url = ss._uid_cgi_snapshot_url(
                "http://192.168.1.110/cgi-bin/getuid",
                "admin",
                "secret",
                3,
            )

        self.assertEqual(
            snapshot_url,
            "http://192.168.1.110/cgi-bin/snapshot.cgi?uid=ABC123",
        )
        session.get.assert_called_once()
        self.assertEqual(
            session.get.call_args.kwargs["params"],
            {"username": "admin", "password": "secret"},
        )
        response.close.assert_called_once()

    def test_uid_cgi_snapshot_url_requires_uid(self):
        response = MagicMock()
        response.ok = True
        response.text = '<?xml version="1.0"?><fault>bad auth</fault>'
        session = MagicMock()
        session.get.return_value = response

        with patch.object(ss, "http_session", return_value=session):
            snapshot_url = ss._uid_cgi_snapshot_url(
                "http://192.168.1.112/cgi-bin/getuid",
                "admin",
                "secret",
                3,
            )

        self.assertIsNone(snapshot_url)
        response.close.assert_called_once()

    def test_browser_capture_profile_detects_hubitat_cloud_dashboard(self):
        profile = ss._browser_capture_profile(
            "https://cloud.hubitat.com/api/hub/apps/52/ui?access_token=x",
            "HubitatBeachEyebat",
        )

        self.assertTrue(profile["allow_private_network_images"])
        self.assertTrue(profile["hubitat_cloud_dashboard"])
        self.assertEqual(profile["auto_dedicated_xpath"], "")
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))
        self.assertGreaterEqual(int(profile["timeout_floor"]), 45)

    def test_hubitat_dashboard_url_detector_supports_v2_and_legacy(self):
        self.assertTrue(
            ss._is_hubitat_cloud_dashboard_url(
                "https://cloud.hubitat.com/api/hub/apps/52/ui?access_token=x"
            )
        )
        self.assertTrue(
            ss._is_hubitat_cloud_dashboard_url(
                "https://cloud.hubitat.com/api/hub/apps/6/dashboard/6?access_token=x"
            )
        )
        self.assertTrue(
            ss._is_hubitat_cloud_dashboard_url(
                "http://192.168.50.129/apps/api/193/dashboard/485?access_token=x"
            )
        )
        self.assertFalse(ss._is_hubitat_cloud_dashboard_url("https://example.com"))

    def test_browser_capture_profile_detects_legacy_hubitat_cloud_dashboard(self):
        profile = ss._browser_capture_profile(
            "https://cloud.hubitat.com/api/hub/apps/6/dashboard/6?access_token=x",
            "HubitatExampleHomeEyebat",
        )

        self.assertTrue(profile["allow_private_network_images"])
        self.assertTrue(profile["hubitat_cloud_dashboard"])
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_browser_capture_profile_detects_local_hubitat_dashboard(self):
        profile = ss._browser_capture_profile(
            "http://192.168.50.129/apps/api/193/dashboard/485?access_token=x",
            "HubitatExterior",
        )

        self.assertTrue(profile["allow_private_network_images"])
        self.assertTrue(profile["hubitat_cloud_dashboard"])
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_browser_profile_chrome_args_enable_rich_graphics_for_flight_tracker(self):
        profile = ss._browser_capture_profile("https://www.flightradar24.com/", "FAA")

        with patch.object(ss, "browser_supports_gl", return_value=True):
            args = ss._browser_profile_chrome_args(profile, "/usr/bin/google-chrome")

        self.assertIn("--enable-webgl", args)
        self.assertIn("--ignore-gpu-blocklist", args)
        self.assertIn("--enable-gpu-rasterization", args)
        self.assertIn("--use-angle=swiftshader", args)
        self.assertIn("--use-gl=egl", args)
        self.assertIn("--window-size=2560,1440", args)
        self.assertNotIn("--disable-gpu", args)

    def test_browser_profile_chrome_args_enable_force_dark_for_visual_filter(self):
        profile = ss._browser_capture_profile(
            "https://app.electricitymaps.com/map", "Energy"
        )

        with patch.object(ss, "browser_supports_gl", return_value=True):
            args = ss._browser_profile_chrome_args(profile, "/usr/bin/google-chrome")

        self.assertIn("--force-dark-mode", args)
        self.assertIn("--enable-features=WebContentsForceDark", args)

    def test_boatnerd_ais_profile_uses_force_dark_visual_filter(self):
        profile = ss._browser_capture_profile(
            "https://ais.boatnerd.com/",
            "BoatnerdAISGreatLakes",
        )

        self.assertTrue(profile["force_dark_visual_filter"])
        self.assertTrue(profile["prefer_rich_graphics"])
        self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

    def test_public_map_dashboard_profile_uses_force_dark_visual_filter(self):
        cases = (
            ("https://www.bing.com/maps?cp=41.99~-87.73", "BingMaps"),
            ("https://earthquake.usgs.gov/earthquakes/map/", "Earthquakes"),
            ("https://embed.waze.com/iframe?zoom=14", "Waze"),
            ("https://www.google.com/maps/@41.96,-87.68,11z", "GoogleMaps"),
            ("https://zoom.earth/#view=42.0,-87.7,21z", "ZoomEarth"),
        )

        for url, name in cases:
            with self.subTest(name=name):
                profile = ss._browser_capture_profile(url, name)
                self.assertTrue(profile["force_dark_visual_filter"])
                self.assertTrue(profile["prefer_rich_graphics"])
                self.assertEqual(tuple(profile["viewport"]), (1920, 1080))

        zoom_profile = ss._browser_capture_profile(
            "https://zoom.earth/#view=42.0,-87.7,21z", "ZoomEarth"
        )
        self.assertIn(".leaflet-popup", tuple(zoom_profile["hide_selectors"]))
        self.assertIn(
            "//*[contains(normalize-space(.),'Welcome to Zoom Earth')]",
            tuple(zoom_profile["popup_xpaths"]),
        )
        self.assertEqual(zoom_profile["auto_dedicated_xpath"], "//body")
        self.assertEqual(zoom_profile["timeout_floor"], 60)
        self.assertEqual(zoom_profile["post_load_delay"], 14.0)

    def test_apply_browser_site_dom_cleanup_returns_removed_count(self):
        driver = MagicMock()
        driver.execute_script.return_value = 4

        removed = ss._apply_browser_site_dom_cleanup(
            driver, ("#modals", "[data-testid='search']"), "FlightRadar"
        )

        self.assertEqual(removed, 4)
        driver.execute_script.assert_called_once()

    def test_apply_browser_site_dom_cleanup_guards_scene_elements(self):
        driver = MagicMock()
        driver.execute_script.return_value = 1

        ss._apply_browser_site_dom_cleanup(driver, ("canvas", ".klaviyo-form"), "Map")

        script = driver.execute_script.call_args.args[0]
        self.assertIn("shouldHideCandidate", script)
        self.assertIn("isSceneTag && frac > 0.05", script)
        self.assertIn("klaviyo", script)
        self.assertIn("account", script)
        self.assertIn("email-capture", script)

    def test_apply_force_dark_visual_filter_injects_scoped_style(self):
        driver = MagicMock()
        driver.execute_script.return_value = True

        applied = ss._apply_force_dark_visual_filter(driver, "Energy")

        self.assertTrue(applied)
        script = driver.execute_script.call_args.args[0]
        self.assertIn("glimpser-force-dark-visual-filter", script)
        self.assertIn("color-scheme", script)
        self.assertIn("invert(1) hue-rotate(180deg)", script)

    def test_apply_force_dark_visual_filter_can_preserve_visual_media(self):
        driver = MagicMock()
        driver.execute_script.return_value = True

        applied = ss._apply_force_dark_visual_filter(
            driver, "APNews", preserve_visual_media=True
        )

        self.assertTrue(applied)
        script = driver.execute_script.call_args.args[0]
        self.assertIn("glimpser-preserve-visual-media", script)
        self.assertIn("preserveVisualMedia", script)
        self.assertIn("img,", script)
        self.assertTrue(driver.execute_script.call_args.args[1])

    def test_apply_force_dark_visual_filter_can_use_theme_mode(self):
        driver = MagicMock()
        driver.execute_script.return_value = True

        applied = ss._apply_force_dark_visual_filter(
            driver, "Modem", preserve_visual_media=False, mode="theme"
        )

        self.assertTrue(applied)
        script = driver.execute_script.call_args.args[0]
        self.assertIn("glimpser-force-dark-theme", script)
        self.assertIn("background-color: #0b1118", script)
        self.assertEqual(driver.execute_script.call_args.args[2], "theme")

    def test_strip_fixed_overlays_guards_scene_elements(self):
        driver = MagicMock()
        driver.execute_script.return_value = 2

        removed = ss._strip_fixed_overlays(driver, "Map")

        self.assertEqual(removed, 2)
        script = driver.execute_script.call_args.args[0]
        self.assertIn("isSceneTag && frac > 0.05", script)
        self.assertIn("hasSceneHint && frac > 0.12", script)
        self.assertIn("wisepops", script)
        self.assertIn("dropdown", script)

    def test_remove_popup_promotes_storefront_text_to_container(self):
        driver = MagicMock()
        driver.find_elements.return_value = [object()]
        driver.execute_script.return_value = True

        removed = ss._remove_popup(
            driver,
            "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'log in for the best experience')]",
        )

        self.assertEqual(removed, 1)
        script = driver.execute_script.call_args.args[0]
        self.assertIn("popupTextTokens", script)
        self.assertIn("log in for the best experience", script)
        self.assertIn("best experience", script)

    def test_hubitat_cloud_dashboard_visual_cleanup_returns_counts(self):
        driver = MagicMock()
        driver.execute_script.return_value = {"hidden": 2, "images": 8, "statuses": 10}

        result = ss._apply_hubitat_cloud_dashboard_visual_cleanup(
            driver, "HubitatBeachEyebat"
        )

        self.assertEqual(result, {"hidden": 2, "images": 8, "statuses": 10})
        driver.execute_script.assert_called_once()

    def test_hubitat_cloud_dashboard_error_reason_rejects_no_response_page(self):
        driver = MagicMock()
        driver.execute_script.return_value = "Pretty-print No response from hub"

        reason = ss._hubitat_cloud_dashboard_error_reason(
            driver,
            "https://cloud.hubitat.com/api/hub/apps/52/ui?access_token=x",
            "HubitatBeachEyebat",
        )

        self.assertEqual(reason, "hubitat_no_response_from_hub")
        driver.execute_script.assert_called_once()

    def test_hubitat_cloud_dashboard_error_reason_rejects_blank_dashboard(self):
        driver = MagicMock()
        driver.execute_script.return_value = {
            "text": "",
            "dashboardItems": 0,
            "images": 0,
            "rounded": 0,
        }

        reason = ss._hubitat_cloud_dashboard_error_reason(
            driver,
            "https://cloud.hubitat.com/api/hub/apps/21/ui?access_token=x",
            "HubitatExampleOfficeMain",
        )

        self.assertEqual(reason, "hubitat_blank_dashboard")
        driver.execute_script.assert_called_once()

    def test_specific_hubitat_preflight_reason_is_preserved(self):
        url = "https://cloud.hubitat.com/api/hub/apps/52/ui?access_token=x"
        previous = ss.throttle_cache.copy()
        try:
            ss.throttle_cache.clear()
            ss.throttle_cache[url] = {"reason": "hubitat_no_response_from_hub"}

            self.assertTrue(ss._has_specific_hubitat_preflight_reason(url))

            ss.throttle_cache[url] = {"reason": "browser_timeout"}
            self.assertFalse(ss._has_specific_hubitat_preflight_reason(url))
        finally:
            ss.throttle_cache.clear()
            ss.throttle_cache.update(previous)

    def test_hubitat_cloud_dashboard_error_reason_ignores_non_hubitat_page(self):
        driver = MagicMock()

        reason = ss._hubitat_cloud_dashboard_error_reason(
            driver,
            "https://example.com/no-response-from-hub",
            "Example",
        )

        self.assertEqual(reason, "")
        driver.execute_script.assert_not_called()

    def test_hubitat_visual_cleanup_recognizes_clean_screenshot_tiles(self):
        script = ss._HUBITAT_CLOUD_DASHBOARD_VISUAL_SCRIPT

        self.assertIn("clean_screenshot", script)
        self.assertIn("img[src*='clean_screenshot']", script)

    def test_browser_selection_skips_lightweight_and_phantom_for_flight_trackers(self):
        self.assertFalse(
            ss.should_use_lightweight_browser(
                "https://www.flightradar24.com/",
                None,
                None,
                False,
                False,
                False,
                False,
                name="FlightRadar",
            )
        )
        self.assertFalse(
            ss.should_use_phantom_browser(
                "https://www.flightaware.com/live/",
                None,
                None,
                False,
                False,
                False,
                False,
                name="FAA",
            )
        )

    def test_browser_selection_skips_lightweight_and_phantom_for_earthcam(self):
        self.assertFalse(
            ss.should_use_lightweight_browser(
                "https://www.earthcam.com/usa/illinois/chicago/midwayairport/?cam=midwayairport",
                None,
                None,
                False,
                False,
                False,
                False,
                name="Midway",
            )
        )
        self.assertFalse(
            ss.should_use_phantom_browser(
                "https://www.earthcam.com/usa/illinois/chicago/midwayairport/?cam=midwayairport",
                None,
                None,
                False,
                False,
                False,
                False,
                name="Midway",
            )
        )

    @patch("app.utils.screenshots.http_session")
    def test_earthcam_extract_stream_url_prefers_embedded_stream(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.text = (
            '"stream":"https:\\/\\/videos-3.earthcam.com\\/fecnetwork\\/22172.flv'
            '\\/playlist.m3u8?t=abc\\u0026td=202604251721"'
        )
        mock_session.return_value.get.return_value = mock_resp

        stream_url = ss._earthcam_extract_stream_url(
            "https://www.earthcam.com/usa/illinois/chicago/midwayairport/?cam=midwayairport"
        )

        self.assertEqual(
            stream_url,
            "https://videos-3.earthcam.com/fecnetwork/22172.flv/playlist.m3u8?t=abc&td=202604251721",
        )
        mock_resp.close.assert_called_once()

    @patch("app.utils.screenshots.http_session")
    def test_earthcam_extract_stream_url_supports_myearthcam_pages(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.text = (
            '"html5_streamingdomain":"https:\\/\\/video1.earthcam.com",'
            '"html5_streampath":"\\/myearthcam\\/abc123.flv\\/playlist.m3u8"'
        )
        mock_session.return_value.get.return_value = mock_resp

        stream_url = ss._earthcam_extract_stream_url(
            "https://myearthcam.com/oakstreetbeach"
        )

        self.assertEqual(
            stream_url,
            "https://video1.earthcam.com/myearthcam/abc123.flv/playlist.m3u8",
        )
        mock_resp.close.assert_called_once()

    @patch("app.utils.screenshots.http_session")
    def test_wetmet_extract_stream_url_uses_signed_hls(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.text = """
        <script>
          var vurl = 'https://wmso-us-ea1.wetmet.net/live/292-02-03/playlist.m3u8?wmsAuthSign=abc&amp;x=1';
          var purl = 'https://wmso-us-ea1.wetmet.net/live/292-02-03/playlist.m3u8?wmsAuthSign=abc&amp;x=1';
        </script>
        """
        mock_session.return_value.get.return_value = mock_resp

        stream_url = ss._wetmet_extract_stream_url(
            "https://api.wetmet.net/widgets/stream/frame.php?uid=a37b23a261c88fec73a98879f937429b",
            timeout=5,
        )

        self.assertEqual(
            stream_url,
            "https://wmso-us-ea1.wetmet.net/live/292-02-03/playlist.m3u8?wmsAuthSign=abc&x=1",
        )
        mock_resp.close.assert_called_once()

    @patch("app.utils.screenshots.http_session")
    def test_rtspme_extract_stream_url_follows_parent_iframe(self, mock_session):
        parent_resp = MagicMock()
        parent_resp.ok = True
        parent_resp.text = '<iframe src="https://rtsp.me/embed/6Bbyenn8/"></iframe>'
        embed_resp = MagicMock()
        embed_resp.ok = True
        embed_resp.text = """
        <script>
          $.get('https://mia.rtsp.me/token/hls/6Bbyenn8.m3u8?ip=10.0.0.1&amp;x=1');
        </script>
        """
        mock_session.return_value.get.side_effect = [parent_resp, embed_resp]

        stream_url = ss._rtspme_extract_stream_url(
            "https://spmarina.net/webcam",
            timeout=5,
        )

        self.assertEqual(
            stream_url,
            "https://mia.rtsp.me/token/hls/6Bbyenn8.m3u8?ip=10.0.0.1&x=1",
        )
        self.assertEqual(mock_session.return_value.get.call_count, 2)
        parent_resp.close.assert_called_once()
        embed_resp.close.assert_called_once()

    def test_ffmpeg_hwaccel_helpers_detect_and_strip_cuda_failure(self):
        stderr = "Cannot load libcuda.so.1; Device creation failed: -1."
        command = ["ffmpeg", "-hide_banner", "-hwaccel", "cuda", "-i", "stream.m3u8"]

        self.assertTrue(ss._ffmpeg_error_suggests_hwaccel_failure(stderr))
        self.assertEqual(
            ss._ffmpeg_command_without_hwaccel(command),
            ["ffmpeg", "-hide_banner", "-i", "stream.m3u8"],
        )

    @patch("app.utils.screenshots.http_session")
    def test_weatherbug_extract_latest_image_prefers_newest_dated_still(
        self, mock_session
    ):
        self.assertTrue(
            ss._is_weatherbug_camera_url(
                "https://www.weatherbug.com/weather-camera/?cam=CRYTH"
            )
        )
        self.assertTrue(
            ss._is_weatherbug_camera_url(
                "https://www.weatherbug.com/weather-camera?cam=CRYTH"
            )
        )
        self.assertTrue(
            ss._is_weatherbug_camera_url(
                "https://www.weatherbug.com/weather-camera/skokie-il-60076/UICIL"
            )
        )
        self.assertFalse(ss._is_weatherbug_camera_url("https://example.com/"))
        self.assertTrue(
            ss._is_limnotech_resized_image_url(
                "https://www.limnotechdata.com/stations/zp-core/i.php?a=Waukegan&i=Waukegan.jpg&s=595"
            )
        )
        self.assertFalse(
            ss._is_limnotech_resized_image_url(
                "https://www.limnotechdata.com/stations/Waukegan/Waukegan.jpg.php"
            )
        )
        self.assertFalse(
            ss._cached_http_failure_blocks_capture(
                503,
                force_browser=False,
                url="https://www.limnotechdata.com/stations/zp-core/i.php?a=Waukegan&i=Waukegan.jpg&s=595",
            )
        )
        self.assertTrue(
            ss._cached_http_failure_blocks_capture(
                503,
                force_browser=False,
                url="https://example.com/image.jpg",
            )
        )

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.text = """
        {"image":"https://cameras-cam.cdn.weatherbug.net/CRYTH/2026/05/01/050120260855_l.jpg"}
        <link rel="preload" as="image" href="https://cameras-cam.cdn.weatherbug.net/CRYTH/2026/05/02/050220260840_l.jpg">
        <link rel="preload" as="image" href="https://cameras-cam.cdn.weatherbug.net/WKGNI/2026/05/02/050220261200_l.jpg">
        https://cameras-cam.cdn.weatherbug.net/CRYTH/2026/05/02/050220260845_l.jpg
        https://cameras-cam.cdn.weatherbug.net/WKGNI/2026/05/02/050220261205_l.jpg
        """
        mock_session.return_value.get.return_value = mock_resp

        image_url = ss._weatherbug_extract_latest_image(
            "https://www.weatherbug.com/weather-camera/?cam=CRYTH",
            timeout=5,
        )

        self.assertEqual(
            image_url,
            "https://cameras-cam.cdn.weatherbug.net/CRYTH/2026/05/02/050220260845_l.jpg",
        )
        mock_resp.close.assert_called_once()

    @patch("app.utils.screenshots.http_session")
    def test_weatherbug_extract_latest_image_supports_slugged_camera_path(
        self, mock_session
    ):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.text = """
        {"image":"https://cameras-cam.cdn.weatherbug.net/UICIL/2026/05/03/050320261010_l.jpg"}
        https://cameras-cam.cdn.weatherbug.net/UICIL/2026/05/03/050320261025_l.jpg
        """
        mock_session.return_value.get.return_value = mock_resp

        image_url = ss._weatherbug_extract_latest_image(
            "https://www.weatherbug.com/weather-camera/skokie-il-60076/UICIL",
            timeout=5,
        )

        self.assertEqual(
            image_url,
            "https://cameras-cam.cdn.weatherbug.net/UICIL/2026/05/03/050320261025_l.jpg",
        )
        mock_resp.close.assert_called_once()

    def test_template_flag_enabled_treats_null_and_zero_as_false(self):
        false_values = [None, "", "0", "false", "False", "no", "off", 0, False]
        true_values = ["1", "true", "yes", "on", 1, True]

        for value in false_values:
            with self.subTest(value=value):
                self.assertFalse(ss._template_flag_enabled(value))
        for value in true_values:
            with self.subTest(value=value):
                self.assertTrue(ss._template_flag_enabled(value))

    def test_earthcam_stream_extraction_respects_browser_forced_templates(self):
        self.assertFalse(ss._earthcam_stream_extraction_allowed(force_browser=True))
        self.assertTrue(ss._earthcam_stream_extraction_allowed(force_browser=False))

    def test_cached_http_failure_does_not_block_forced_browser(self):
        self.assertTrue(
            ss._cached_http_failure_blocks_capture(403, force_browser=False)
        )
        self.assertTrue(
            ss._cached_http_failure_blocks_capture(429, force_browser=False)
        )
        self.assertFalse(
            ss._cached_http_failure_blocks_capture(403, force_browser=True)
        )
        self.assertFalse(
            ss._cached_http_failure_blocks_capture(None, force_browser=False)
        )

    def test_browser_capture_lock_path_can_be_overridden(self):
        lock_path = os.path.join(self.tmpdir, "browser.lock")

        with patch.dict(os.environ, {"GLIMPSER_BROWSER_CAPTURE_LOCK": lock_path}):
            self.assertEqual(ss._browser_capture_lock_path(), lock_path)

    def test_browser_capture_file_lock_writes_owner_metadata(self):
        lock_path = os.path.join(self.tmpdir, "browser.lock")

        with patch.dict(os.environ, {"GLIMPSER_BROWSER_CAPTURE_LOCK": lock_path}):
            acquired, lock_file = ss._acquire_browser_capture_file_lock("FAA", 0.1)
            try:
                self.assertTrue(acquired)
                self.assertIsNotNone(lock_file)
                with open(lock_path, encoding="utf-8") as handle:
                    metadata = handle.read()
                self.assertIn("name=FAA", metadata)
                self.assertIn("pid=", metadata)
            finally:
                ss._release_browser_capture_file_lock(lock_file, "FAA")

    def test_is_color_bars_pattern_detects_vertical_test_pattern(self):
        colors = [
            (255, 255, 0),
            (0, 255, 255),
            (0, 255, 0),
            (255, 0, 255),
            (255, 0, 0),
            (0, 0, 255),
            (0, 0, 0),
        ]
        frame = Image.new("RGB", (280, 160), (0, 0, 0))
        draw = ImageDraw.Draw(frame)
        for idx, color in enumerate(colors):
            left = idx * 40
            draw.rectangle((left, 0, left + 39, 159), fill=color)

        self.assertTrue(ss.is_color_bars_pattern(frame))
        self.assertEqual(ss._captured_frame_rejection_reason(frame), "test_pattern")

    def test_is_color_bars_pattern_ignores_structured_scene(self):
        frame = Image.new("RGB", (280, 160), (18, 24, 34))
        draw = ImageDraw.Draw(frame)
        draw.rectangle((20, 20, 120, 78), fill=(90, 130, 180))
        draw.rectangle((150, 28, 258, 138), fill=(55, 82, 104))
        draw.ellipse((56, 84, 116, 144), fill=(210, 180, 90))
        draw.line((0, 159, 279, 0), fill=(255, 255, 255), width=3)

        self.assertFalse(ss.is_color_bars_pattern(frame))
        self.assertIsNone(ss._captured_frame_rejection_reason(frame))

    def test_captured_frame_rejects_sparse_dark_loading_frame(self):
        frame = Image.new("RGB", (760, 430), (14, 14, 14))
        draw = ImageDraw.Draw(frame)
        draw.arc((360, 190, 400, 230), 20, 310, fill=(210, 210, 210), width=3)

        self.assertIn(ss._captured_frame_rejection_reason(frame), {"blank", "loading"})

    def test_captured_frame_keeps_dark_textured_camera_frame(self):
        frame = Image.new("RGB", (760, 430), (12, 12, 12))
        draw = ImageDraw.Draw(frame)
        for x in range(0, 760, 18):
            draw.line((x, 0, 760 - x // 2, 429), fill=(36, 40, 42), width=2)
        draw.rectangle((70, 240, 690, 380), fill=(32, 34, 36))
        draw.line((20, 370, 740, 250), fill=(75, 75, 72), width=3)

        self.assertIsNone(ss._captured_frame_rejection_reason(frame))

    def test_captured_frame_keeps_colored_page_with_text(self):
        frame = Image.new("RGB", (760, 430), (21, 94, 117))
        draw = ImageDraw.Draw(frame)
        draw.text((120, 190), "glimpser screenshot smoke", fill=(255, 255, 255))

        self.assertIsNone(ss._captured_frame_rejection_reason(frame))

    def test_stabilize_captured_image_aligns_previous_frame(self):
        camera_dir = os.path.join(self.tmpdir, "crib")
        os.makedirs(camera_dir, exist_ok=True)
        reference_path = os.path.join(camera_dir, "crib_20260420000000.png")

        reference = Image.new("RGB", (180, 120), (20, 20, 20))
        draw = ImageDraw.Draw(reference)
        draw.rectangle((24, 18, 76, 74), fill=(225, 225, 225))
        draw.line((110, 12, 146, 92), fill=(255, 120, 120), width=6)
        draw.ellipse((118, 70, 160, 112), fill=(80, 180, 255))
        reference.save(reference_path, format="PNG")

        shifted = Image.new("RGB", (180, 120), (20, 20, 20))
        draw = ImageDraw.Draw(shifted)
        draw.rectangle((31, 22, 83, 78), fill=(225, 225, 225))
        draw.line((117, 16, 153, 96), fill=(255, 120, 120), width=6)
        draw.ellipse((125, 74, 167, 116), fill=(80, 180, 255))

        final_path = os.path.join(camera_dir, "crib_20260421000000.png")
        stabilized = ss._stabilize_captured_image(
            shifted, final_path, "crib", "previous"
        )

        before = np.abs(
            np.asarray(shifted, dtype=np.int16) - np.asarray(reference, dtype=np.int16)
        ).mean()
        after = np.abs(
            np.asarray(stabilized, dtype=np.int16)
            - np.asarray(reference, dtype=np.int16)
        ).mean()

        self.assertLess(after, before * 0.75)

    def test_stabilize_captured_image_skips_old_rolling_reference(self):
        camera_dir = os.path.join(self.tmpdir, "crib_old")
        os.makedirs(camera_dir, exist_ok=True)
        reference_path = os.path.join(camera_dir, "crib_old_20260420000000.png")

        reference = Image.new("RGB", (120, 80), (30, 30, 30))
        reference.save(reference_path, format="PNG")
        stale_time = time.time() - 7200
        os.utime(reference_path, (stale_time, stale_time))

        current = Image.new("RGB", (120, 80), (30, 30, 30))
        final_path = os.path.join(camera_dir, "crib_old_20260421000000.png")
        stabilized = ss._stabilize_captured_image(
            current, final_path, "crib_old", "rolling_5m"
        )

        self.assertTrue(
            np.array_equal(
                np.asarray(current, dtype=np.uint8),
                np.asarray(stabilized, dtype=np.uint8),
            )
        )

    def test_burst_enhance_full_frame_upscales_low_res_camera(self):
        camera_dir = os.path.join(self.tmpdir, "lowres")
        os.makedirs(camera_dir, exist_ok=True)
        for idx, shift in enumerate((0, 1, 0), start=1):
            frame = Image.new("RGB", (120, 80), (24, 28, 32))
            draw = ImageDraw.Draw(frame)
            draw.rectangle((18 + shift, 16, 54 + shift, 48), fill=(215, 215, 225))
            draw.line((68, 14, 102, 60), fill=(96, 180, 255), width=4)
            frame.save(
                os.path.join(camera_dir, f"lowres_2026042100000{idx}.png"),
                format="PNG",
            )

        current = Image.new("RGB", (120, 80), (24, 28, 32))
        draw = ImageDraw.Draw(current)
        draw.rectangle((19, 16, 55, 48), fill=(215, 215, 225))
        draw.line((68, 14, 102, 60), fill=(96, 180, 255), width=4)
        final_path = os.path.join(camera_dir, "lowres_20260421000100.png")

        enhanced = ss._enhance_captured_image(
            current,
            final_path,
            "lowres",
            "full_frame",
            "hybrid",
            "",
        )

        self.assertEqual(enhanced.size, (240, 160))

    def test_burst_enhance_roi_turns_selected_crop_into_zoom_view(self):
        camera_dir = os.path.join(self.tmpdir, "grow_zoom")
        os.makedirs(camera_dir, exist_ok=True)
        reference = Image.new("RGB", (200, 100), (22, 22, 22))
        draw = ImageDraw.Draw(reference)
        draw.rectangle((120, 25, 165, 75), fill=(220, 220, 210))
        draw.ellipse((132, 35, 154, 57), fill=(120, 210, 120))
        reference.save(
            os.path.join(camera_dir, "grow_zoom_20260421000000.png"),
            format="PNG",
        )

        current = Image.new("RGB", (200, 100), (22, 22, 22))
        draw = ImageDraw.Draw(current)
        draw.rectangle((120, 25, 165, 75), fill=(220, 220, 210))
        draw.ellipse((132, 35, 154, 57), fill=(120, 210, 120))
        final_path = os.path.join(camera_dir, "grow_zoom_20260421000100.png")

        enhanced = ss._enhance_captured_image(
            current,
            final_path,
            "grow_zoom",
            "roi",
            "clean",
            "118,24,52,52",
        )

        self.assertEqual(enhanced.size, current.size)
        original_gray = np.asarray(current.convert("L"), dtype=np.uint8)
        enhanced_gray = np.asarray(enhanced.convert("L"), dtype=np.uint8)
        self.assertFalse(np.array_equal(original_gray, enhanced_gray))
        original_bright_ratio = float((original_gray > 150).mean())
        enhanced_bright_ratio = float((enhanced_gray > 150).mean())
        self.assertGreater(enhanced_bright_ratio, original_bright_ratio)

    def test_postprocess_still_image_applies_capture_crop_roi(self):
        current = Image.new("RGB", (200, 120), (10, 10, 10))
        draw = ImageDraw.Draw(current)
        draw.rectangle((20, 30, 139, 89), fill=(220, 180, 90))
        final_path = os.path.join(self.tmpdir, "capture_crop.png")

        with patch(
            "app.utils.template_manager.get_template",
            return_value={
                "capture_crop_roi": "20,30,120,60",
                "burst_enhance_mode": "",
                "composite_view_mode": "",
                "night_enhance_mode": "",
            },
        ):
            cropped = ss._postprocess_still_image(
                current,
                final_path,
                "capture_crop",
                remove_bg=False,
            )

        self.assertEqual(cropped.size, (120, 60))
        self.assertEqual(cropped.getpixel((0, 0)), (220, 180, 90))

    def test_postprocess_still_image_applies_rotation_and_lens_correction(self):
        current = Image.new("RGB", (120, 80), (20, 40, 80))
        draw = ImageDraw.Draw(current)
        draw.rectangle((20, 16, 100, 64), fill=(80, 180, 120))
        draw.line((0, 40, 119, 40), fill=(240, 240, 240), width=3)
        final_path = os.path.join(self.tmpdir, "fisheye_cam.png")

        with patch(
            "app.utils.template_manager.get_template",
            return_value={
                "capture_rotate_degrees": -90,
                "lens_correction_spec": ("rectilinear:fov=95,src_fov=180,zoom=1.15"),
                "capture_crop_roi": "",
                "burst_enhance_mode": "",
                "composite_view_mode": "",
                "night_enhance_mode": "",
            },
        ):
            corrected = ss._postprocess_still_image(
                current,
                final_path,
                "fisheye_cam",
                remove_bg=False,
            )

        self.assertEqual(corrected.size, (80, 120))
        self.assertGreater(float(np.asarray(corrected).mean()), 10.0)
        rotated_only = current.transpose(Image.Transpose.ROTATE_90)
        self.assertFalse(
            np.array_equal(np.asarray(corrected), np.asarray(rotated_only))
        )

    def test_horizon_level_estimates_sloped_horizon(self):
        current = Image.new("RGB", (240, 140), (174, 202, 232))
        pixels = current.load()
        slope = np.tan(np.radians(4.0))
        for x in range(current.width):
            horizon_y = int(58 + slope * (x - current.width / 2))
            for y in range(horizon_y, current.height):
                pixels[x, y] = (42, 92, 112)
        estimate = ss._estimate_horizon_level_angle(current)

        self.assertIsNotNone(estimate)
        assert estimate is not None
        angle, confidence = estimate
        self.assertGreater(angle, 2.5)
        self.assertLess(angle, 5.5)
        self.assertGreater(confidence, ss._HORIZON_LEVEL_MIN_CONFIDENCE)

    def test_horizon_level_estimates_buoy_roll_beyond_six_degrees(self):
        current = Image.new("RGB", (240, 140), (174, 202, 232))
        pixels = current.load()
        slope = np.tan(np.radians(10.0))
        for x in range(current.width):
            horizon_y = int(58 + slope * (x - current.width / 2))
            for y in range(max(0, horizon_y), current.height):
                pixels[x, y] = (42, 92, 112)
        estimate = ss._estimate_horizon_level_angle(current)

        self.assertIsNotNone(estimate)
        assert estimate is not None
        angle, confidence = estimate
        self.assertGreater(angle, 8.0)
        self.assertLess(angle, 12.0)
        self.assertGreater(confidence, ss._HORIZON_LEVEL_MIN_CONFIDENCE)

    def test_postprocess_still_image_applies_horizon_level(self):
        current = Image.new("RGB", (240, 140), (174, 202, 232))
        pixels = current.load()
        slope = np.tan(np.radians(4.0))
        for x in range(current.width):
            horizon_y = int(58 + slope * (x - current.width / 2))
            for y in range(horizon_y, current.height):
                pixels[x, y] = (42, 92, 112)
        final_path = os.path.join(self.tmpdir, "buoy.png")

        with patch(
            "app.utils.template_manager.get_template",
            return_value={
                "horizon_level_mode": "roll",
                "horizon_level_roi": "",
                "capture_crop_roi": "",
                "capture_rotate_degrees": 0,
                "lens_correction_spec": "",
                "burst_enhance_mode": "",
                "composite_view_mode": "",
                "night_enhance_mode": "",
            },
        ):
            leveled = ss._postprocess_still_image(
                current,
                final_path,
                "buoy",
                remove_bg=False,
            )

        before = ss._estimate_horizon_level_angle(current)
        after = ss._estimate_horizon_level_angle(leveled)
        self.assertIsNotNone(before)
        self.assertTrue(after is None or abs(after[0]) < abs(before[0]))

    def test_smooth_horizon_level_uses_half_current_roll_for_small_change(self):
        camera_dir = os.path.join(self.tmpdir, "smooth_buoy")
        os.makedirs(camera_dir, exist_ok=True)
        final_path = os.path.join(camera_dir, "smooth_buoy_20260509000000.png")
        state_path = os.path.join(camera_dir, "horizon_level_state.json")
        with open(state_path, "w", encoding="utf-8") as fh:
            fh.write('{"angle": 8.0}')

        smoothed = ss._smooth_horizon_level_angle(10.0, final_path, "smooth_buoy")

        self.assertEqual(smoothed, 9.0)

    def test_smooth_horizon_level_resets_on_large_angle_jump(self):
        camera_dir = os.path.join(self.tmpdir, "smooth_rotator")
        os.makedirs(camera_dir, exist_ok=True)
        final_path = os.path.join(camera_dir, "smooth_rotator_20260509000000.png")
        state_path = os.path.join(camera_dir, "horizon_level_state.json")
        with open(state_path, "w", encoding="utf-8") as fh:
            fh.write('{"angle": 8.0}')

        smoothed = ss._smooth_horizon_level_angle(1.0, final_path, "smooth_rotator")

        self.assertEqual(smoothed, 1.0)

    def test_burst_enhance_neutralizes_bottom_right_timestamp_overlay(self):
        camera_dir = os.path.join(self.tmpdir, "overlay_cam")
        os.makedirs(camera_dir, exist_ok=True)

        reference = Image.new("RGB", (180, 120), (30, 30, 30))
        draw = ImageDraw.Draw(reference)
        draw.rectangle((32, 24, 96, 88), fill=(180, 220, 200))
        draw.rectangle((128, 94, 176, 116), fill=(255, 255, 255))
        reference.save(
            os.path.join(camera_dir, "overlay_cam_20260421000000.png"),
            format="PNG",
        )

        current = Image.new("RGB", (180, 120), (30, 30, 30))
        draw = ImageDraw.Draw(current)
        draw.rectangle((32, 24, 96, 88), fill=(180, 220, 200))
        final_path = os.path.join(camera_dir, "overlay_cam_20260421000100.png")

        enhanced = ss._enhance_captured_image(
            current,
            final_path,
            "overlay_cam",
            "full_frame",
            "clean",
            "",
        )

        overlay_region = np.asarray(enhanced.convert("L"), dtype=np.float32)[-26:, -52:]
        self.assertLess(float(overlay_region.mean()), 100.0)

    def test_night_enhance_lifts_dark_static_scene(self):
        camera_dir = os.path.join(self.tmpdir, "night_cam")
        os.makedirs(camera_dir, exist_ok=True)
        rng = np.random.default_rng(1234)

        base = np.full((90, 140, 3), 18, dtype=np.uint8)
        base[24:68, 38:92] = np.array([52, 68, 86], dtype=np.uint8)
        base[34:56, 56:76] = np.array([118, 132, 148], dtype=np.uint8)

        for idx in range(3):
            noisy = np.clip(
                base.astype(np.int16)
                + rng.integers(-9, 10, size=base.shape, dtype=np.int16),
                0,
                255,
            ).astype(np.uint8)
            Image.fromarray(noisy, mode="RGB").save(
                os.path.join(camera_dir, f"night_cam_2026042100000{idx}.png"),
                format="PNG",
            )

        current = np.clip(
            base.astype(np.int16)
            + rng.integers(-10, 11, size=base.shape, dtype=np.int16),
            0,
            255,
        ).astype(np.uint8)
        current_image = Image.fromarray(current, mode="RGB")
        final_path = os.path.join(camera_dir, "night_cam_20260421000100.png")

        enhanced = ss._night_enhance_captured_image(
            current_image,
            final_path,
            "night_cam",
            "medium",
        )

        original_gray = np.asarray(current_image.convert("L"), dtype=np.float32)
        enhanced_gray = np.asarray(enhanced.convert("L"), dtype=np.float32)
        background_slice = np.s_[0:20, 0:20]

        self.assertGreater(
            float(enhanced_gray.mean()), float(original_gray.mean()) + 8.0
        )
        self.assertLess(
            float(enhanced_gray[background_slice].std()),
            float(original_gray[background_slice].std()),
        )

    def test_night_enhance_skips_bright_scene(self):
        current = Image.new("RGB", (120, 80), (180, 186, 190))
        final_path = os.path.join(self.tmpdir, "bright_cam_20260421000100.png")

        enhanced = ss._night_enhance_captured_image(
            current,
            final_path,
            "bright_cam",
            "strong",
        )

        self.assertTrue(
            np.array_equal(
                np.asarray(current, dtype=np.uint8),
                np.asarray(enhanced, dtype=np.uint8),
            )
        )

    def test_render_composite_view_grid_places_each_panel(self):
        current = Image.new("RGB", (400, 200), (10, 10, 10))
        draw = ImageDraw.Draw(current)
        draw.rectangle((0, 0, 199, 99), fill=(220, 40, 40))
        draw.rectangle((200, 0, 399, 99), fill=(40, 220, 40))
        draw.rectangle((0, 100, 199, 199), fill=(40, 40, 220))
        draw.rectangle((200, 100, 399, 199), fill=(220, 220, 40))

        rendered = ss._render_composite_view(
            current,
            "grid",
            (
                "Red@0,0,0.5,0.5;"
                "Green@0.5,0,0.5,0.5;"
                "Blue@0,0.5,0.5,0.5;"
                "Yellow@0.5,0.5,0.5,0.5"
            ),
            "quad_cam",
        )

        boxes = ss._composite_layout_boxes("grid", current.size, 4)
        pixels = np.asarray(rendered, dtype=np.uint8)
        label_height = max(28, min(42, current.size[1] // 18))

        def sample_color(box):
            left, top, right, bottom = box
            y = top + label_height + max(10, (bottom - top - label_height) // 2)
            x = left + max(10, (right - left) // 2)
            return pixels[y, x]

        red = sample_color(boxes[0])
        green = sample_color(boxes[1])
        blue = sample_color(boxes[2])
        yellow = sample_color(boxes[3])
        self.assertGreater(int(red[0]), int(red[1]) + 100)
        self.assertGreater(int(green[1]), int(green[0]) + 100)
        self.assertGreater(int(blue[2]), int(blue[1]) + 100)
        self.assertGreater(int(yellow[0]), 150)
        self.assertGreater(int(yellow[1]), 150)

    def test_postprocess_still_image_applies_composite_view(self):
        current = Image.new("RGB", (320, 160), (18, 18, 18))
        draw = ImageDraw.Draw(current)
        draw.rectangle((100, 20, 220, 140), fill=(200, 180, 60))
        draw.ellipse((130, 45, 170, 85), fill=(70, 180, 90))
        final_path = os.path.join(self.tmpdir, "composite_cam.png")

        with (
            patch(
                "app.utils.screenshots.remove_background", side_effect=lambda img: img
            ),
            patch(
                "app.utils.screenshots._stabilize_captured_image",
                side_effect=lambda img, *_args, **_kwargs: img,
            ),
            patch(
                "app.utils.template_manager.get_template",
                return_value={
                    "burst_enhance_mode": "",
                    "burst_enhance_profile": "",
                    "burst_enhance_roi": "",
                    "composite_view_mode": "hero_strip",
                    "composite_view_spec": (
                        "Direct@0.28,0.12,0.44,0.76;"
                        "Leaf@0.40,0.26,0.14,0.14;"
                        "Pot@0.31,0.20,0.16,0.16"
                    ),
                },
            ),
        ):
            rendered = ss._postprocess_still_image(current, final_path, "composite_cam")

        self.assertEqual(rendered.size, current.size)
        self.assertFalse(
            np.array_equal(
                np.asarray(current, dtype=np.uint8),
                np.asarray(rendered, dtype=np.uint8),
            )
        )

    def test_postprocess_still_image_does_not_invert_dark_camera_frames(self):
        current = Image.new("RGB", (96, 54), (0, 0, 0))
        draw = ImageDraw.Draw(current)
        draw.rectangle((8, 8, 40, 30), fill=(22, 22, 22))
        draw.rectangle((56, 16, 84, 38), fill=(180, 180, 180))
        final_path = os.path.join(self.tmpdir, "dark_cam.png")

        with (
            patch(
                "app.utils.screenshots._stabilize_captured_image",
                side_effect=lambda img, *_args, **_kwargs: img,
            ),
            patch("app.utils.template_manager.get_template", return_value={}),
        ):
            rendered = ss._postprocess_still_image(
                current,
                final_path,
                "dark_cam",
                dark=True,
                remove_bg=False,
            )

        self.assertTrue(
            np.array_equal(
                np.asarray(current, dtype=np.uint8),
                np.asarray(rendered, dtype=np.uint8),
            )
        )

    def test_postprocess_still_image_darkens_allowlisted_static_chart(self):
        current = Image.new("RGB", (160, 90), (248, 248, 248))
        draw = ImageDraw.Draw(current)
        draw.line((8, 45, 152, 45), fill=(8, 8, 8), width=3)
        draw.rectangle((24, 18, 136, 72), outline=(30, 70, 180), width=2)
        final_path = os.path.join(self.tmpdir, "icecover.png")

        with (
            patch(
                "app.utils.screenshots._stabilize_captured_image",
                side_effect=lambda img, *_args, **_kwargs: img,
            ),
            patch(
                "app.utils.template_manager.get_template",
                return_value={
                    "url": (
                        "https://www.glerl.noaa.gov/data/ice/spaghetti/"
                        "mic_ice_compare.png"
                    ),
                    "capture_crop_roi": "",
                    "burst_enhance_mode": "",
                    "composite_view_mode": "",
                    "night_enhance_mode": "",
                },
            ),
        ):
            rendered = ss._postprocess_still_image(
                current,
                final_path,
                "IceCover",
                dark=True,
                remove_bg=False,
            )

        luma = np.asarray(rendered.convert("L"), dtype=np.uint8)
        self.assertLess(float(luma.mean()), 80.0)
        self.assertGreater(float((luma <= 64).mean()), 0.85)
        self.assertGreater(rendered.getpixel((80, 45))[0], 240)

    def test_static_chart_dark_mode_allowlist_covers_public_chart_urls(self):
        cases = (
            (
                "Drought",
                "https://droughtmonitor.unl.edu/data/png/current/current_midwest_trd.png",
            ),
            (
                "McCookHydrograph",
                "https://water.noaa.gov/resources/hydrographs/mcci2_hg.png",
            ),
            (
                "SWPCSpaceWeatherOverview",
                "https://services.swpc.noaa.gov/images/swx-overview-large.gif",
            ),
            ("NOAA", "https://www.weather.gov/wwamap/png/lot.png"),
            (
                "APS",
                "https://www3.aps.anl.gov/asd/operations/gifplots/HDSRcomfort.png",
            ),
        )

        for name, url in cases:
            with self.subTest(name=name):
                self.assertTrue(
                    ss._static_chart_dark_mode_enabled(
                        name,
                        {"url": url},
                        True,
                    )
                )
                self.assertFalse(
                    ss._static_chart_dark_mode_enabled(
                        name,
                        {"url": url},
                        False,
                    )
                )

    def test_download_image_reprocesses_unchanged_static_chart_dark_mode(self):
        current = Image.new("RGB", (160, 90), (248, 248, 248))
        draw = ImageDraw.Draw(current)
        draw.line((8, 45, 152, 45), fill=(8, 8, 8), width=3)
        buffer = BytesIO()
        current.save(buffer, format="PNG")
        payload = buffer.getvalue()
        url = "https://www.glerl.noaa.gov/data/ice/spaghetti/mic_ice_compare.png"
        ss._set_image_hash(url, hashlib.sha256(payload).hexdigest())

        class FakeResponse:
            status_code = 200
            headers = {}

            def __init__(self, content):
                self.content = content

            def close(self):
                return None

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse(payload)

        output_path = os.path.join(self.tmpdir, "icecover_download.png")
        with (
            patch("app.utils.screenshots.http_session", return_value=FakeSession()),
            patch(
                "app.utils.screenshots.remove_background", side_effect=lambda img: img
            ),
            patch(
                "app.utils.screenshots._stabilize_captured_image",
                side_effect=lambda img, *_args, **_kwargs: img,
            ),
            patch("app.utils.screenshots.add_timestamp", return_value=None),
            patch(
                "app.utils.template_manager.get_template",
                return_value={
                    "url": url,
                    "capture_crop_roi": "",
                    "burst_enhance_mode": "",
                    "composite_view_mode": "",
                    "night_enhance_mode": "",
                },
            ),
        ):
            self.assertTrue(
                ss.download_image(url, output_path, name="IceCover", dark=True)
            )

        luma = np.asarray(Image.open(output_path).convert("L"), dtype=np.uint8)
        self.assertLess(float(luma.mean()), 80.0)
        self.assertGreater(float((luma <= 64).mean()), 0.85)

    def test_capture_reprocesses_not_modified_static_chart_dark_mode(self):
        url = "https://www.glerl.noaa.gov/data/ice/spaghetti/mic_ice_compare.png"
        template = {
            "url": url,
            "dark": True,
            "invert": False,
            "browser": False,
            "danger": False,
            "headless": True,
            "timeout": 30,
        }

        with (
            patch("app.utils.screenshots._tier_allowed", return_value=True),
            patch("app.utils.screenshots._preflight_dns_tls", return_value=(True, "")),
            patch("app.utils.screenshots.is_address_reachable", return_value=True),
            patch(
                "app.utils.screenshots.get_content_type",
                return_value=("image/png", False, True, "not_modified"),
            ),
            patch(
                "app.utils.screenshots.download_image", return_value=True
            ) as mock_download,
        ):
            result = ss._capture_or_download_inner(
                "IceCover",
                template,
                url,
                url,
                None,
                None,
            )

        self.assertTrue(result)
        mock_download.assert_called_once()
        self.assertTrue(mock_download.call_args.args[5])

    def test_download_image_runs_burst_enhance_for_direct_stills(self):
        current = Image.new("RGB", (200, 100), (22, 22, 22))
        draw = ImageDraw.Draw(current)
        draw.rectangle((120, 25, 165, 75), fill=(220, 220, 210))
        draw.ellipse((132, 35, 154, 57), fill=(120, 210, 120))
        buffer = BytesIO()
        current.save(buffer, format="PNG")
        payload = buffer.getvalue()

        class FakeResponse:
            status_code = 200
            headers = {}

            def __init__(self, content):
                self.content = content

            def close(self):
                return None

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse(payload)

        output_path = os.path.join(self.tmpdir, "roi_download.png")
        with (
            patch("app.utils.screenshots.http_session", return_value=FakeSession()),
            patch(
                "app.utils.screenshots.remove_background", side_effect=lambda img: img
            ),
            patch(
                "app.utils.screenshots._stabilize_captured_image",
                side_effect=lambda img, *_args, **_kwargs: img,
            ),
            patch("app.utils.screenshots.add_timestamp", return_value=None),
            patch(
                "app.utils.template_manager.get_template",
                return_value={
                    "burst_enhance_mode": "roi",
                    "burst_enhance_profile": "clean",
                    "burst_enhance_roi": "118,24,52,52",
                },
            ),
        ):
            self.assertTrue(
                ss.download_image(
                    "http://example.com/test.png",
                    output_path,
                    name="roi_download",
                )
            )

        enhanced = Image.open(output_path).convert("L")
        original = current.convert("L")
        original_bright_ratio = float((np.asarray(original) > 150).mean())
        enhanced_bright_ratio = float((np.asarray(enhanced) > 150).mean())
        self.assertGreater(enhanced_bright_ratio, original_bright_ratio)

    def test_download_image_rejects_color_bar_test_pattern(self):
        colors = [
            (255, 255, 0),
            (0, 255, 255),
            (0, 255, 0),
            (255, 0, 255),
            (255, 0, 0),
            (0, 0, 255),
            (0, 0, 0),
        ]
        current = Image.new("RGB", (280, 160), (0, 0, 0))
        draw = ImageDraw.Draw(current)
        for idx, color in enumerate(colors):
            left = idx * 40
            draw.rectangle((left, 0, left + 39, 159), fill=color)

        buffer = BytesIO()
        current.save(buffer, format="PNG")
        payload = buffer.getvalue()

        class FakeResponse:
            status_code = 200
            headers = {}

            def __init__(self, content):
                self.content = content

            def close(self):
                return None

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse(payload)

        output_path = os.path.join(self.tmpdir, "bars_download.png")
        with patch("app.utils.screenshots.http_session", return_value=FakeSession()):
            self.assertFalse(
                ss.download_image(
                    "http://example.com/test-bars.png",
                    output_path,
                    name="bars_download",
                )
            )

        self.assertFalse(os.path.exists(output_path))

    def test_resolve_ytdlp_video_url_uses_module_when_cli_missing(self):
        ydl_instance = MagicMock()
        ydl_instance.extract_info.return_value = {
            "url": "https://video.example/live.m3u8"
        }
        ydl_context = MagicMock()
        ydl_context.__enter__.return_value = ydl_instance
        ydl_context.__exit__.return_value = False

        with (
            patch("app.utils.screenshots.shutil.which", return_value=None),
            patch(
                "app.utils.screenshots.youtube_dl.YoutubeDL",
                return_value=ydl_context,
            ),
            patch("app.utils.screenshots.subprocess.run") as mock_run,
        ):
            status, video_url = ss._resolve_ytdlp_video_url(
                "https://www.youtube.com/watch?v=test"
            )

        self.assertEqual(status, "good")
        self.assertEqual(video_url, "https://video.example/live.m3u8")
        mock_run.assert_not_called()

    def test_capture_frame_with_ytdlp_uses_module_fallback_when_cli_missing(self):
        output_path = os.path.join(self.tmpdir, "youtube_capture.png")
        ydl_instance = MagicMock()
        ydl_instance.extract_info.return_value = {
            "url": "https://video.example/live.m3u8"
        }
        ydl_context = MagicMock()
        ydl_context.__enter__.return_value = ydl_instance
        ydl_context.__exit__.return_value = False

        def fake_ffmpeg_run(command, **_kwargs):
            Image.new("RGB", (40, 24), (30, 60, 90)).save(output_path, format="PNG")
            return MagicMock(returncode=0)

        with (
            patch("app.utils.screenshots._check_ffmpeg", return_value=True),
            patch("app.utils.screenshots.shutil.which", return_value=None),
            patch(
                "app.utils.screenshots.youtube_dl.YoutubeDL",
                return_value=ydl_context,
            ),
            patch(
                "app.utils.screenshots.subprocess.run", side_effect=fake_ffmpeg_run
            ) as mock_run,
            patch(
                "app.utils.screenshots._postprocess_still_image",
                side_effect=lambda image, *_args, **_kwargs: image,
            ),
            patch("app.utils.screenshots.add_timestamp", return_value=None),
        ):
            self.assertTrue(
                ss.capture_frame_with_ytdlp(
                    "https://www.youtube.com/watch?v=test",
                    output_path,
                    name="yt_fallback",
                )
            )

        self.assertTrue(os.path.exists(output_path))
        ffmpeg_command = mock_run.call_args[0][0]
        self.assertNotIn("-hwaccel", ffmpeg_command)

    def test_cleanup_orphaned_browser_processes_reaps_only_stale_orphans(self):
        class FakeProcess:
            def __init__(self, pid, ppid, name, create_time, children=None):
                self.pid = pid
                self.info = {
                    "pid": pid,
                    "ppid": ppid,
                    "name": name,
                    "create_time": create_time,
                }
                self._children = children or []
                self.terminated = False
                self.killed = False

            def ppid(self):
                return self.info["ppid"]

            def name(self):
                return self.info["name"]

            def create_time(self):
                return self.info["create_time"]

            def children(self, recursive=False):
                return list(self._children)

            def terminate(self):
                self.terminated = True

            def kill(self):
                self.killed = True

            def is_running(self):
                return True

        now = 10_000.0
        stale_child = FakeProcess(101, 100, "chromium", now - 3_700)
        stale_root = FakeProcess(
            100,
            1,
            "chromedriver",
            now - 3_700,
            children=[stale_child],
        )
        active_root = FakeProcess(200, os.getpid(), "chromedriver", now - 3_700)
        young_root = FakeProcess(300, 1, "chromedriver", now - 30)
        unrelated_root = FakeProcess(400, 1, "chromium", now - 3_700)

        ss._ORPHAN_BROWSER_CLEANUP_LAST = 0.0
        with (
            patch("app.utils.screenshots.time.time", return_value=now),
            patch(
                "app.utils.screenshots.psutil.process_iter",
                return_value=[stale_root, active_root, young_root, unrelated_root],
            ),
            patch(
                "app.utils.screenshots.psutil.wait_procs",
                side_effect=lambda procs, timeout: ([], procs),
            ),
        ):
            cleaned = ss.cleanup_orphaned_browser_processes(
                max_age_seconds=1_800,
                force=True,
            )

        self.assertEqual(cleaned, 2)
        self.assertTrue(stale_root.terminated)
        self.assertTrue(stale_root.killed)
        self.assertTrue(stale_child.terminated)
        self.assertTrue(stale_child.killed)
        self.assertFalse(active_root.terminated)
        self.assertFalse(young_root.terminated)
        self.assertFalse(unrelated_root.terminated)

    def test_cleanup_orphaned_browser_processes_throttles_scans(self):
        ss._ORPHAN_BROWSER_CLEANUP_LAST = 1_000.0

        with (
            patch("app.utils.screenshots.time.time", return_value=1_001.0),
            patch("app.utils.screenshots.psutil.process_iter") as process_iter,
        ):
            cleaned = ss.cleanup_orphaned_browser_processes(force=False)

        self.assertEqual(cleaned, 0)
        process_iter.assert_not_called()

    def test_private_https_preflight_skips_tls_when_ssl_verify_disabled(self):
        ss.dns_cache.clear()
        ss.dns_cache_time.clear()
        ss.tls_cache.clear()
        ss.tls_cache_time.clear()

        with (
            patch(
                "app.utils.screenshots.socket.getaddrinfo",
                return_value=[
                    (
                        None,
                        None,
                        None,
                        "",
                        ("192.168.50.1", 443),
                    )
                ],
            ),
            patch("app.utils.screenshots.config.REQUEST_VERIFY_SSL", False),
            patch("app.utils.screenshots.ssl.create_default_context") as make_context,
        ):
            ok, reason = ss._preflight_dns_tls(
                "https://io.home.lollie.org/bandwidthd/example.png"
            )

        self.assertTrue(ok)
        self.assertEqual(reason, "tls_skipped_private")
        make_context.assert_not_called()

    def test_public_https_preflight_skips_tls_when_ssl_verify_disabled(self):
        ss.dns_cache.clear()
        ss.dns_cache_time.clear()
        ss.tls_cache.clear()
        ss.tls_cache_time.clear()

        with (
            patch(
                "app.utils.screenshots.socket.getaddrinfo",
                return_value=[
                    (
                        None,
                        None,
                        None,
                        "",
                        ("93.184.216.34", 443),
                    )
                ],
            ),
            patch("app.utils.screenshots.config.REQUEST_VERIFY_SSL", False),
            patch("app.utils.screenshots.ssl.create_default_context") as make_context,
        ):
            ok, reason = ss._preflight_dns_tls(
                "https://public-camera.example.invalid/snapshot.jpg"
            )

        self.assertTrue(ok)
        self.assertEqual(reason, "tls_skipped_verify_disabled")
        make_context.assert_not_called()


if __name__ == "__main__":
    unittest.main()
