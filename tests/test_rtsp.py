import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from unittest.mock import patch

from app import create_app
import app.routes as routes


class TestRTSP(unittest.TestCase):
    def setUp(self):
        self.app = create_app(watchdog=False, schedule=False)
        self.app.testing = True
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()
        routes.rtsp_sessions.clear()

    def test_rtsp_handshake_and_stream(self):
        # OPTIONS
        resp = self.client.open("/test.rtsp", method="OPTIONS", headers={"CSeq": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Public", resp.data)

        # DESCRIBE
        resp = self.client.open("/test.rtsp", method="DESCRIBE", headers={"CSeq": "2"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/sdp")

        # SETUP
        resp = self.client.open(
            "/test.rtsp",
            method="SETUP",
            headers={"CSeq": "3", "Transport": "RTP/AVP"},
        )
        self.assertEqual(resp.status_code, 200)
        session_id = resp.headers.get("Session")
        self.assertIsNotNone(session_id)
        self.assertIn(session_id, routes.rtsp_sessions)
        self.assertEqual(routes.rtsp_sessions[session_id]["state"], "READY")

        # PLAY
        resp = self.client.open(
            "/test.rtsp",
            method="PLAY",
            headers={"CSeq": "4", "Session": session_id},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Session"), session_id)
        self.assertEqual(routes.rtsp_sessions[session_id]["state"], "PLAYING")

        # GET_PARAMETER not implemented
        resp = self.client.open(
            "/test.rtsp",
            method="GET_PARAMETER",
            headers={"CSeq": "5", "Session": session_id},
        )
        self.assertEqual(resp.status_code, 405)

        # rtsp_stream should return RTP packets when PLAYING
        fake_frame = b"JPEGDATA"
        rtp_header = b"\x80\x60\x00\x01\x00\x00\x00\x01\x00\x00\x00\x01"

        def fake_generate(group=None, filename="latest_camera.png", rtsp=False, session_id=None):
            def gen():
                if rtsp:
                    yield rtp_header + fake_frame
                else:
                    yield fake_frame
            return gen()

        with patch("app.routes.generate", side_effect=fake_generate):
            resp = self.client.get(f"/rtsp_stream?session={session_id}")
            self.assertEqual(resp.status_code, 200)
            chunk = next(resp.response)
            self.assertTrue(chunk.startswith(rtp_header))

        # TEARDOWN
        resp = self.client.open(
            "/test.rtsp",
            method="TEARDOWN",
            headers={"CSeq": "6", "Session": session_id},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(session_id, routes.rtsp_sessions)


if __name__ == "__main__":
    unittest.main()
