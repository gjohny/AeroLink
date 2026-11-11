from datetime import timedelta
from functools import wraps

from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import Trip
from ..trips import current_user
from .models import WeatherPlan, WeatherEvent, utcnow
from . import providers
from .service import ensure_plan, validate_settings, local_window, refresh_trip, weather_result

weather_api = Blueprint("weather", __name__, url_prefix="/api")


def owned_trip(function):
    @wraps(function)
    def wrapped(trip_id, **kwargs):
        user = current_user()
        if not user:
            return jsonify(error="Not authenticated."), 401
        trip = db.session.execute(db.select(Trip).filter_by(id=trip_id, user_id=user.id)).scalar_one_or_none()
        if not trip:
            return jsonify(error="Trip not found."), 404
        return function(trip, **kwargs)
    return wrapped


@weather_api.get("/weather/locations")
def search_locations():
    if not current_user():
        return jsonify(error="Not authenticated."), 401
    query = request.args.get("q", "").strip()
    if not 2 <= len(query) <= 200:
        return jsonify(error="Enter between 2 and 200 characters."), 400
    try:
        return jsonify(locations=providers.locations(query))
    except providers.ProviderError as exc:
        return jsonify(error=str(exc)), 503


@weather_api.get("/trips/<int:trip_id>/weather-plan")
@owned_trip
def get_plan(trip):
    plan = db.session.get(WeatherPlan, trip.id)
    return jsonify(plan=plan.settings if plan else None, revision=plan.revision if plan else None)


@weather_api.put("/trips/<int:trip_id>/weather-plan")
@owned_trip
def save_plan(trip):
    try:
        settings = validate_settings(request.get_json(silent=True))
        for leg, day, location in (("outbound", trip.start_date, settings.get("origin")),
                                    ("return", trip.end_date, settings["destination"])):
            if location:
                local_window(day, location, settings.get(f"{leg}_time"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    plan = db.session.get(WeatherPlan, trip.id)
    now = utcnow()
    if plan and plan.lease_until and plan.lease_until > now:
        return jsonify(error="A weather refresh is running. Try saving again when it finishes."), 409
    if not plan:
        plan = WeatherPlan(trip_id=trip.id, settings=settings)
        db.session.add(plan)
    elif plan.settings != settings:
        plan.settings = settings
        plan.revision += 1
        plan.routes = {}
        plan.last_error = None
        plan.last_attempt_at = None
    plan.next_refresh_at = now
    db.session.commit()
    return jsonify(plan=plan.settings, revision=plan.revision)


@weather_api.get("/trips/<int:trip_id>/weather")
@owned_trip
def get_weather(trip):
    try:
        plan = ensure_plan(trip)
    except providers.ProviderError as exc:
        return jsonify(status="setup_required", setup_required=True, forecast=None, last_error=str(exc))
    if not plan:
        return jsonify(status="setup_required", setup_required=True, forecast=None,
                       last_error="Confirm your destination using location search to start weather monitoring.")
    # Reads never block on dozens of route forecasts; worker/manual refresh does that work.
    return jsonify(**weather_result(plan))


@weather_api.post("/trips/<int:trip_id>/weather/refresh")
@owned_trip
def refresh_weather(trip):
    plan = db.session.get(WeatherPlan, trip.id)
    if not plan:
        return jsonify(error="Save a weather plan before refreshing."), 400
    if plan.last_attempt_at and plan.last_attempt_at > utcnow() - timedelta(seconds=60):
        return jsonify(error="Please wait a minute before refreshing again."), 429
    refreshed = refresh_trip(trip.id)
    db.session.expire_all()
    plan = db.session.get(WeatherPlan, trip.id)
    if not plan:
        return jsonify(error="Trip not found."), 404
    return jsonify(**weather_result(plan), refreshed=refreshed)


@weather_api.get("/trips/<int:trip_id>/weather/events")
@owned_trip
def list_events(trip):
    events = db.session.execute(db.select(WeatherEvent).filter_by(trip_id=trip.id)
                               .order_by(WeatherEvent.id.desc()).limit(100)).scalars().all()
    return jsonify(events=[event.to_dict() for event in events])


@weather_api.post("/trips/<int:trip_id>/weather/events/<int:event_id>/read")
@owned_trip
def read_event(trip, event_id):
    event = db.session.execute(db.select(WeatherEvent).filter_by(id=event_id, trip_id=trip.id)).scalar_one_or_none()
    if not event:
        return jsonify(error="Weather event not found."), 404
    event.is_read = True
    db.session.commit()
    return jsonify(event=event.to_dict())
