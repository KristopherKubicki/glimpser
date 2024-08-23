from flask import Blueprint

auth = Blueprint("auth", __name__)
main = Blueprint("main", __name__)
api = Blueprint("api", __name__)
stream = Blueprint("stream", __name__)
template = Blueprint("template", __name__)

from . import auth, main, api, stream, template


def init_app(app):
    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(api)
    app.register_blueprint(stream)
    app.register_blueprint(template)
