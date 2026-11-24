from datetime import date
from math import isfinite

from flask import Blueprint, jsonify, request, session
from requests.exceptions import RequestException

from .geoapify_service import get_places

from .extensions import db
from .models import User, Trip, TravelPreference, SavedPlace, RecommendationFeedback
from .destination_images import find_destination_photo
from .rec_ranker import rank_recommendations

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

    # Delete saved places before deleting their parent trip.
    db.session.execute(
        db.delete(SavedPlace).where(SavedPlace.trip_id == trip.id)
    )
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


@trips_api.patch('/<int:trip_id>/preferences')
def update_trip_preferences(trip_id):
    user = current_user()
    if not user:
        return jsonify(error='Not authenticated.'), 401

    trip = db.session.execute(
        db.select(Trip).filter_by(id=trip_id, user_id=user.id)
    ).scalar_one_or_none()

    if not trip:
        return jsonify(error='Trip not found.'), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Invalid request.'), 400

    raw = data.get('preferences')
    if not isinstance(raw, dict):
        return jsonify(error='Invalid trip preferences.'), 400

    updated = {}
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
            return jsonify(
                error=f'Invalid {field} preferences.'
            ), 400

        cleaned = []
        seen = set()

        for item in items:
            value = item.strip()
            if value.casefold() not in seen:
                cleaned.append(value)
                seen.add(value.casefold())

        updated[field] = cleaned

    trip.preference_snapshot = updated
    db.session.commit()

    return jsonify(trip=trip.to_dict()), 200


def owned_trip(trip_id):
    user = current_user()

    if not user:
        return None, 401

    trip = db.session.execute(
        db.select(Trip).filter_by(
            id=trip_id,
            user_id=user.id,
        )
    ).scalar_one_or_none()

    if not trip:
        return None, 404

    return trip, None


@trips_api.get("/<int:trip_id>/saved-places")
def list_saved_places(trip_id):
    trip, error = owned_trip(trip_id)

    if error:
        return jsonify(
            error="Not authenticated." if error == 401
            else "Trip not found."
        ), error

    places = db.session.execute(
        db.select(SavedPlace)
        .filter_by(trip_id=trip.id)
        .order_by(SavedPlace.created_at, SavedPlace.id)
    ).scalars().all()

    return jsonify(
        places=[place.to_dict() for place in places]
    ), 200


@trips_api.post("/<int:trip_id>/saved-places")
def save_place(trip_id):
    trip, error = owned_trip(trip_id)

    if error:
        return jsonify(
            error="Not authenticated." if error == 401
            else "Trip not found."
        ), error

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(error="Invalid place data."), 400

    def string_field(key, limit, required=False):
        value = data.get(key, "")

        if value is None and not required:
            return ""

        if not isinstance(value, str):
            raise ValueError(f"Invalid {key}.")

        value = value.strip()

        if len(value) > limit or (required and not value):
            raise ValueError(f"Invalid {key}.")

        return value

    try:
        place_key = string_field("place_key", 100, True)
        name = string_field("name", 200, True)
        category = string_field("category", 30, True)
        detail = string_field("detail", 500)
        price = string_field("price", 100)
        image = string_field("image", 1000)
        why = string_field("why", 1000)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    metadata = data.get("place_metadata", {})
    if not isinstance(metadata, dict):
        return jsonify(error="Invalid place metadata."), 400
    # Store a small, known set of display fields only.
    allowed = ("address", "latitude", "longitude", "website", "phone",
               "catering", "facilities", "osm_tags", "categories",
               "photo_credit", "photo_source_url")
    metadata = {key: metadata[key] for key in allowed if key in metadata}
    if len(str(metadata)) > 12000:
        return jsonify(error="Place metadata is too large."), 400
    for key in ("latitude", "longitude"):
        value = metadata.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)):
            return jsonify(error="Invalid coordinates."), 400
    for key in ("address", "website", "phone", "photo_credit", "photo_source_url"):
        if key in metadata and not isinstance(metadata[key], str):
            return jsonify(error="Invalid place metadata."), 400
    for key in ("catering", "facilities", "osm_tags"):
        if key in metadata and not isinstance(metadata[key], dict):
            return jsonify(error="Invalid place metadata."), 400
    if "categories" in metadata and (not isinstance(metadata["categories"], list) or any(not isinstance(v, str) for v in metadata["categories"])):
        return jsonify(error="Invalid place metadata."), 400

    if category not in (
        "activities",
        "restaurants",
        "accommodation",
    ):
        return jsonify(error="Invalid category."), 400

    existing = db.session.execute(
        db.select(SavedPlace).filter_by(
            trip_id=trip.id,
            place_key=place_key,
        )
    ).scalar_one_or_none()

    if existing:
        return jsonify(place=existing.to_dict()), 200

    place = SavedPlace(
        trip_id=trip.id,
        place_key=place_key,
        name=name,
        category=category,
        detail=detail,
        price=price,
        image_url=image,
        why=why,
        place_metadata=metadata,
    )

    db.session.add(place)
    db.session.commit()

    return jsonify(place=place.to_dict()), 201


@trips_api.delete(
    "/<int:trip_id>/saved-places/<int:place_id>"
)
def remove_saved_place(trip_id, place_id):
    trip, error = owned_trip(trip_id)

    if error:
        return jsonify(
            error="Not authenticated." if error == 401
            else "Trip not found."
        ), error

    place = db.session.execute(
        db.select(SavedPlace).filter_by(
            id=place_id,
            trip_id=trip.id,
        )
    ).scalar_one_or_none()

    if not place:
        return jsonify(error="Saved place not found."), 404

    db.session.delete(place)
    db.session.commit()

    return jsonify(message="Place removed."), 200


@trips_api.route("/<int:trip_id>/recommendations", methods=["GET", "POST"])
def get_trip_recommendations(trip_id):
    # Verify authentication and trip ownership.
    trip, error = owned_trip(trip_id)

    if error:
        return jsonify(
            error="Not authenticated." if error == 401
            else "Trip not found."
        ), error

    # Read and validate the requested category.
    category = request.args.get("category", "activities")

    valid_categories = (
        "activities",
        "restaurants",
        "accommodation",
    )

    if category not in valid_categories:
        return jsonify(
            error="Invalid recommendation category."
        ), 400

    # POST requests are used by "Find New Places". Keep the
    # original GET behavior for normal loading and feedback refresh.
    excluded_ids = []
    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Invalid refresh request."), 400
        excluded_ids = payload.get("excluded_ids", [])
        if (
            not isinstance(excluded_ids, list)
            or len(excluded_ids) > 200
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in excluded_ids
            )
        ):
            return jsonify(error="Invalid excluded place IDs."), 400
        excluded_ids = list(dict.fromkeys(excluded_ids))

    feedback_records = db.session.execute(
        db.select(RecommendationFeedback)
        .filter_by(trip_id=trip.id)
    ).scalars().all()

    feedback_data = [
        record.to_dict()
        for record in feedback_records
    ]

    # Retrieve real places using the trip destination.
    try:
        places = get_places(
            destination=trip.destination,
            category=category,
            limit=20,
            preferences=trip.preference_snapshot or {},
            feedback_records=feedback_data,
            excluded_ids=excluded_ids,
        )

    except RequestException:
        return jsonify(
            error="Unable to retrieve recommendations right now."
        ), 502

    except RuntimeError:
        return jsonify(
            error="Recommendations service is not configured."
        ), 503

    return jsonify(
        destination=trip.destination,
        category=category,
        recommendations=places,
        exhausted=bool(request.method == "POST" and not places),
    ), 200


@trips_api.get("/<int:trip_id>/feedback")
def get_recommendation_feedback(trip_id):
    trip, error = owned_trip(trip_id)

    if error:
        return jsonify(
            error="Not authenticated." if error == 401
            else "Trip not found."
        ), error

    records = db.session.execute(
        db.select(RecommendationFeedback)
        .filter_by(trip_id=trip.id)
    ).scalars().all()

    return jsonify(
        feedback=[record.to_dict() for record in records]
    ), 200


@trips_api.put("/<int:trip_id>/feedback/<place_key>")
def update_recommendation_feedback(trip_id, place_key):
    trip, error = owned_trip(trip_id)

    if error:
        return jsonify(
            error="Not authenticated." if error == 401
            else "Trip not found."
        ), error

    if len(place_key) != 64 or any(
        char not in "0123456789abcdef"
        for char in place_key
    ):
        return jsonify(error="Invalid place ID."), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(error="Invalid feedback."), 400

    preference = data.get("preference")
    category = data.get("category")
    categories = data.get("place_categories", [])

    if preference not in ("more", "less", None):
        return jsonify(error="Invalid feedback choice."), 400

    if category not in (
        "activities", "restaurants", "accommodation"
    ):
        return jsonify(error="Invalid category."), 400

    if (
        not isinstance(categories, list)
        or len(categories) > 50
        or any(
            not isinstance(value, str)
            or not 1 <= len(value) <= 100
            for value in categories
        )
    ):
        return jsonify(error="Invalid place categories."), 400

    existing = db.session.execute(
        db.select(RecommendationFeedback).filter_by(
            trip_id=trip.id,
            place_key=place_key,
        )
    ).scalar_one_or_none()

    if preference is None:
        if existing:
            db.session.delete(existing)
    elif existing:
        existing.preference = preference
        existing.category = category
        existing.place_categories = categories
    else:
        db.session.add(
            RecommendationFeedback(
                trip_id=trip.id,
                place_key=place_key,
                category=category,
                preference=preference,
                place_categories=categories,
            )
        )

    db.session.commit()

    return jsonify(
        place_key=place_key,
        preference=preference,
    ), 200


@trips_api.get("/<int:trip_id>/itinerary-selections")
def list_itinerary_selections(trip_id):
    trip, error = owned_trip(trip_id)
    if error:
        return jsonify(error="Not authenticated." if error == 401 else "Trip not found."), error
    places = db.session.execute(
        db.select(SavedPlace).filter_by(trip_id=trip.id, added_to_itinerary=True)
        .order_by(SavedPlace.created_at, SavedPlace.id)
    ).scalars().all()
    return jsonify(places=[place.to_dict() for place in places])


@trips_api.patch("/<int:trip_id>/saved-places/itinerary")
@trips_api.patch("/<int:trip_id>/saved-places/<int:place_id>/itinerary")
def update_itinerary_selection(trip_id, place_id=None):
    trip, error = owned_trip(trip_id)
    if error:
        return jsonify(error="Not authenticated." if error == 401 else "Trip not found."), error
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("added_to_itinerary"), bool):
        return jsonify(error="Expected a boolean added_to_itinerary."), 400
    query = db.select(SavedPlace).filter_by(trip_id=trip.id)
    if place_id is not None:
        query = query.filter_by(id=place_id)
    places = db.session.execute(query.order_by(SavedPlace.created_at, SavedPlace.id)).scalars().all()
    if place_id is not None and not places:
        return jsonify(error="Saved place not found."), 404
    for place in places:
        place.added_to_itinerary = data["added_to_itinerary"]
    db.session.commit()
    return jsonify(places=[place.to_dict() for place in places])
