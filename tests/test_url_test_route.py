import http.server
import os
import threading
from unittest.mock import patch

import pytest
import requests
from werkzeug.serving import make_server

from app import create_app


class ServerThread(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", 0, app)
        self.port = self.server.server_port

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture()
def tmp_http_server(tmp_path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield server
    server.shutdown()
    thread.join()


def test_url_test_endpoint(tmp_http_server):
    with patch("app.routes.login_required", lambda x: x):
        app = create_app(enable_watchdog=False, schedule=False, log_cache=False)
        server = ServerThread(app)
        server.start()
        try:
            url = f"http://127.0.0.1:{tmp_http_server.server_port}"
            resp = requests.get(
                f"http://127.0.0.1:{server.port}/templates/test_url",
                params={"url": url},
            )
            data = resp.json()
            assert resp.status_code == 200
            assert data["ok"]
            assert data["kind"] == "webpage"
            assert data["suggestions"]["browser"] is True
        finally:
            server.shutdown()
