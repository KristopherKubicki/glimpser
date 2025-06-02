import os
import tempfile
import argparse
import importlib
from threading import Thread
from werkzeug.serving import make_server

import generate_credentials
import app.config as config
import app.utils.db as db
import app.routes as routes
import app


class ServerThread(Thread):
    def __init__(self, app, port: int):
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", port, app)

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


def main(port: int = 5000):
    data_dir = tempfile.mkdtemp(prefix="pwdata")
    db_path = os.path.join(data_dir, "test.db")

    args = argparse.Namespace(
        db_path=db_path,
        username="e2e",
        password="secret",
        update_password=False,
        secret_key="secretkey",
        update_key=False,
    )
    generate_credentials.generate_credentials(args)

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(routes)
    importlib.reload(app)

    application = app.create_app(enable_watchdog=False, schedule=False)

    server = ServerThread(application, port)
    server.start()
    print("Server started", flush=True)
    try:
        server.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PW_PORT", "5000"))
    main(port)
