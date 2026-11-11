"""Trip weather forecasts, explainable advisories, and background monitoring."""
import time
from datetime import timedelta, timezone
import click
from sqlalchemy import or_
from ..extensions import db
from ..models import Trip
from .models import WeatherPlan, WeatherProviderCache, utcnow


def check_due(now=None):
    from .service import ensure_plan, refresh_trip, monitoring_end
    from .providers import ProviderError
    now = now or utcnow()
    # Auto-resolve only unambiguous destinations entering the forecast horizon.
    candidates = db.session.execute(db.select(Trip).outerjoin(WeatherPlan, Trip.id == WeatherPlan.trip_id)
        .where(WeatherPlan.trip_id.is_(None), Trip.end_date >= (now - timedelta(days=1)).date(),
               Trip.start_date <= (now + timedelta(days=16)).date())).scalars().all()
    for trip in candidates:
        try:
            ensure_plan(trip)
        except ProviderError:
            pass
    due = db.session.execute(db.select(WeatherPlan.trip_id).where(WeatherPlan.next_refresh_at <= now,
        or_(WeatherPlan.lease_until.is_(None), WeatherPlan.lease_until < now))).scalars().all()
    count = 0
    for trip_id in due:
        trip, plan = db.session.get(Trip, trip_id), db.session.get(WeatherPlan, trip_id)
        if trip and monitoring_end(trip, plan.settings) > now.replace(tzinfo=timezone.utc):
            count += bool(refresh_trip(trip_id, now))
    # Cache data is disposable; keep the database bounded without touching snapshots.
    db.session.execute(db.delete(WeatherProviderCache).where(WeatherProviderCache.expires_at < now - timedelta(days=7),
        or_(WeatherProviderCache.retry_at.is_(None), WeatherProviderCache.retry_at < now)))
    db.session.commit()
    return count


def register_weather(app):
    from .routes import weather_api
    app.register_blueprint(weather_api)

    @app.cli.command("weather-worker")
    @click.option("--once", is_flag=True, help="Check due trips once, then exit.")
    def weather_worker(once):
        """Run exactly one external worker; never start threads in Flask's reloader."""
        while True:
            try:
                count = check_due()
                click.echo(f"Weather monitoring: refreshed {count} trip(s).")
            except Exception:
                db.session.rollback()
                app.logger.exception("Weather monitoring pass failed")
            finally:
                db.session.remove()
            if once:
                break
            time.sleep(app.config["WEATHER_WORKER_INTERVAL_SECONDS"])
