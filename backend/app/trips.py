
from datetime import date
from math import isfinite

from flask import Blueprint, jsonify, request, session

from .extensions import db
from .models import User, Trip, TravelPreference
from .destination_images import find_destination_photo


trips_api = Blueprint("trips_api", __name__, url_prefix="/api/trips")

FIELDS = (
    "interests",
    "cuisines",
    "dietary_restrictions",
    "accommodation_types",
    "amenities",
)


def current_user():
    user_id = session.get("user_id")
    return (
        db.session.get(User, user_id)
        if isinstance(user_id, int)
        else None
    )


def defaults(user_id):
    saved = db.session.execute(
        db.select(TravelPreference).filter_by(user_id=user_id)
    ).scalar_one_or_none()

    return {
        key: list(getattr(saved, key) or []) if saved else []
        for key in FIELDS
    }


def parse_trip(data, user_id):
    if not isinstance(data, dict):
        raise ValueError("Enter valid trip details.")

    destination = data.get("destination")

    if (
        not isinstance(destination, str)
        or not 1 <= len(destination.strip()) <= 200
    ):
        raise ValueError(
            "Destination is required (maximum 200 characters)."
        )

    try:
        start = date.fromisoformat(data["start_date"])
        end = date.fromisoformat(data["end_date"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Enter valid start and end dates.")

    if end < start:
        raise ValueError(
            "End date must be on or after the start date."
        )

    raw_budget = data.get("budget")

    try:
        budget = (
            float(raw_budget)
            if raw_budget not in (None, "")
            else None
        )
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Budget must be a valid number.")

    if budget is not None and (
        not isfinite(budget) or budget < 0
    ):
        raise ValueError("Budget cannot be negative.")

    travelers = data.get("travelers", 1)

    if (
        isinstance(travelers, bool)
        or not isinstance(travelers, int)
        or not 1 <= travelers <= 100
    ):
        raise ValueError(
            "Travelers must be between 1 and 100."
        )

    use_saved = data.get(
        "use_saved_preferences", True
    )

    if not isinstance(use_saved, bool):
        raise ValueError(
            "Invalid preference selection."
        )

    if use_saved:
        snapshot = defaults(user_id)
    else:
        raw = data.get("preferences", {})

        if not isinstance(raw, dict):
            raise ValueError(
                "Invalid trip preferences."
            )

        snapshot = {}

        for field in FIELDS:
            items = raw.get(field, [])

            if (
                not isinstance(items, list)
                or len(items) > 50
                or any(
                    not isinstance(item, str)
                    or not item.strip()
                    or len(item) > 100
                    for item in items
                )
            ):
                raise ValueError(
                    f"Invalid {field} preferences."
                )

            snapshot[field] = list(items)

    return {
        "destination": destination.strip(),
        "start_date": start,
        "end_date": end,
        "budget": budget,
        "travelers": travelers,
        "preference_snapshot": snapshot,
    }


@trips_api.get("")
def list_trips():
    user = current_user()

    if not user:
        return jsonify(
            error="Not authenticated."
        ), 401

    trips = db.session.execute(
        db.select(Trip)
        .filter_by(user_id=user.id)
        .order_by(
            Trip.start_date.desc(),
            Trip.id.desc(),
        )
    ).scalars().all()

    return jsonify(
        trips=[trip.to_dict() for trip in trips]
    )


@trips_api.post("")
def create_trip():
    user = current_user()

    if not user:
        return jsonify(
            error="Not authenticated."
        ), 401

    try:
        values = parse_trip(
            request.get_json(silent=True),
            user.id,
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    # Find an Unsplash photo for the destination.
    # If none is available, the trip is still created.
    photo = find_destination_photo(
        values["destination"]
    )

    trip = Trip(
        user_id=user.id,
        **values,
        **(photo or {}),
    )

    db.session.add(trip)
    db.session.commit()

    return jsonify(
        trip=trip.to_dict()
    ), 201


@trips_api.get("/<int:trip_id>")
def get_trip(trip_id):
    user = current_user()

    if not user:
        return jsonify(
            error="Not authenticated."
        ), 401

    trip = db.session.execute(
        db.select(Trip).filter_by(
            id=trip_id,
            user_id=user.id,
        )
    ).scalar_one_or_none()

    if not trip:
        return jsonify(
            error="Trip not found."
        ), 404

    return jsonify(
        trip=trip.to_dict()
    ), 200


@trips_api.delete("/<int:trip_id>")
def delete_trip(trip_id):
    user = current_user()

    if not user:
        return jsonify(
            error="Not authenticated."
        ), 401

    trip = db.session.execute(
        db.select(Trip).filter_by(
            id=trip_id,
            user_id=user.id,
        )
    ).scalar_one_or_none()

    if not trip:
        return jsonify(
            error="Trip not found."
        ), 404

    db.session.delete(trip)
    db.session.commit()

    return jsonify(
        message="Trip deleted."
    )


@trips_api.post("/<int:trip_id>/photo")
def update_trip_photo(trip_id):
    user = current_user()

    if not user:
        return jsonify(
            error="Not authenticated."
        ), 401

    trip = db.session.execute(
        db.select(Trip).filter_by(
            id=trip_id,
            user_id=user.id,
        )
    ).scalar_one_or_none()

    if not trip:
        return jsonify(
            error="Trip not found."
        ), 404

    photo = find_destination_photo(
        trip.destination
    )

    if not photo:
        return jsonify(
            error=(
                "No destination photo available. "
                "Check your Unsplash API key "
                "or try again later."
            )
        ), 503

    trip.image_url = photo["image_url"]
    trip.image_credit = photo["image_credit"]

    db.session.commit()

    return jsonify(
        trip=trip.to_dict()
    )
