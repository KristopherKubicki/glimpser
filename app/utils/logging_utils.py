import logging
from logging.handlers import RotatingFileHandler
import os


def setup_logging(app):
    # Ensure log directory exists
    log_dir = os.path.join(app.root_path, "..", "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Set up file handler
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=10,
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        )
    )
    file_handler.setLevel(logging.INFO)

    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    console_handler.setLevel(logging.DEBUG)

    # Add handlers to the app logger
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)

    # Set up werkzeug logger
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.addHandler(file_handler)
    werkzeug_logger.addHandler(console_handler)
    werkzeug_logger.setLevel(logging.DEBUG)

    app.logger.info("Logging setup completed")


def log_error(app, error_message):
    app.logger.error(f"Error occurred: {error_message}")


def log_info(app, info_message):
    app.logger.info(info_message)


def log_warning(app, warning_message):
    app.logger.warning(warning_message)
