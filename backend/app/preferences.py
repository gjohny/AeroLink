
from datetime import date
from math import isfinite

from flask import Blueprint, jsonify, request, session

from .extensions import db
from .models import TravelPreference, User

preferences_api = Blueprint(
    "preferences_api",
    __name__,
    url_prefix="/api/preferences"
)

LIST_FIELDS = (
    "interests",
    "cuisines",
    "dietary_restrictions",
    "accommodation_types",
    "amenities",
)


def current_user():
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        return None
    return db.session.get(User, user_id)


@preferences_api.get("")
def get_preferences():
    user = current_user()

    if user is None:
        return jsonify(error="Not authenticated."), 401

    preference = db.session.execute(
        db.select(TravelPreference).filter_by(user_id=user.id)
    ).scalar_one_or_none()

    return jsonify(
        preferences=preference.to_dict() if preference else None
    )


@preferences_api.put("")
def save_preferences():
    user = current_user()

    if user is None:
        return jsonify(error="Not authenticated."), 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(error="Invalid JSON object."), 400

    preference = db.session.execute(
        db.select(TravelPreference).filter_by(user_id=user.id)
    ).scalar_one_or_none()

    if preference is None:
        preference = TravelPreference(user_id=user.id)
        db.session.add(preference)

    destination = data.get("destination") or ""
    if not isinstance(destination, str) or len(destination) > 200:
        return jsonify(error="Invalid destination."), 400

    preference.destination = destination.strip() or None

    try:
        start = (
            date.fromisoformat(data["start_date"])
            if data.get("start_date") else None
        )
        end = (
            date.fromisoformat(data["end_date"])
            if data.get("end_date") else None
        )
    except (TypeError, ValueError):
        return jsonify(error="Invalid travel dates."), 400

    if start and end and end < start:
        return jsonify(error="End date must follow start date."), 400

    preference.start_date = start
    preference.end_date = end

    budget = data.get("budget")

    if budget is not None:
        try:
            if isinstance(budget, bool):
                raise ValueError()
            budget = float(budget)
        except (TypeError, ValueError, OverflowError):
            return jsonify(error="Invalid budget."), 400

        if not isfinite(budget) or budget < 0 or budget > 1_000_000_000:
            return jsonify(error="Invalid budget."), 400

    preference.budget = budget

    travelers = data.get("travelers", 1)

    if type(travelers) is not int or not 1 <= travelers <= 50:
        return jsonify(error="Travelers must be between 1 and 50."), 400

    preference.travelers = travelers

    for field in LIST_FIELDS:
        values = data.get(field, [])

        if (
            not isinstance(values, list)
            or len(values) > 50
            or any(
                not isinstance(value, str) or len(value) > 100
                for value in values
            )
        ):
            return jsonify(error=f"Invalid {field}."), 400

        setattr(preference, field, list(dict.fromkeys(values)))

    db.session.commit()

    return jsonify(
        message="Preferences saved successfully.",
        preferences=preference.to_dict()
    )
