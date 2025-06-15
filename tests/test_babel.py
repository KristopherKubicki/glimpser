from flask_babel import Babel

from app import create_app
from app.config import LANG


def test_babel_default_locale():
    app = create_app(enable_watchdog=False, schedule=False, log_cache=False)
    babel = app.extensions.get("babel")
    assert isinstance(babel, Babel)
    assert app.config["BABEL_DEFAULT_LOCALE"] == LANG
