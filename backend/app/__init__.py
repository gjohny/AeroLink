from flask import Flask
from config import Config

from .extensions import cors, db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from .routes import api

    app.register_blueprint(api)

    from .auth import auth

    app.register_blueprint(auth)

    from .preferences import preferences_api

    app.register_blueprint(preferences_api)

    with app.app_context():
        from . import models  # noqa: F401  (registers models)

        db.create_all()  # creates tables on first run

    return app
