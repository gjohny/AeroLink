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

    from .airports import airports_api
    app.register_blueprint(airports_api)

    from .flights import flights_api
    app.register_blueprint(flights_api)

    from .auth import auth

    app.register_blueprint(auth)

    from .preferences import preferences_api

    app.register_blueprint(preferences_api)

    from .trips import trips_api

    app.register_blueprint(trips_api)

    from .trip_sharing import sharing_api

    app.register_blueprint(sharing_api)

    from .alerts.routes import alerts_bp

    app.register_blueprint(alerts_bp)

    from .alerts.flight_plan import flight_plan_bp

    app.register_blueprint(flight_plan_bp)

    from .alerts.stored_flights import lookup_bp

    app.register_blueprint(lookup_bp)

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
