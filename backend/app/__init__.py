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

    from .trips import trips_api
    app.register_blueprint(trips_api)

    with app.app_context():
        from . import models  # noqa: F401  (registers models)

        db.create_all()  # creates tables on first run
        # Add missing columns to existing local SQLite databases.
        if db.engine.dialect.name == "sqlite":
            with db.engine.begin() as conn:
                columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(saved_places)")}
                if "place_metadata" not in columns:
                    conn.exec_driver_sql("ALTER TABLE saved_places ADD COLUMN place_metadata JSON")
                if "added_to_itinerary" not in columns:
                    conn.exec_driver_sql("ALTER TABLE saved_places ADD COLUMN added_to_itinerary BOOLEAN NOT NULL DEFAULT 0")

    return app
