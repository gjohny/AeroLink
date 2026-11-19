"""
Trip sharing: the owner creates a code, and another user enters it to join the trip.

Both people then see the same trip row, so any change to the trip shows up for both.
Only the owner can share or delete the trip. A member can only leave it.
The owner can also stop sharing with one person or with everyone, without deleting the trip.
"""

import secrets

from flask import Blueprint, jsonify, request, session

from .extensions import db
from .models import Trip, TripMember, TripShareCode, User

sharing_api = Blueprint("sharing_api", __name__, url_prefix = "/api/trips")

# No 0/O or 1/I/L, so a code read aloud or typed by hand is less likely to be mistyped
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


# Helpers, also used by trips.py

def is_member(trip, user):
    membership = db.session.execute(db.select(TripMember).filter_by(trip_id = trip.id, user_id = user.id)).scalar_one_or_none()
    
    return membership is not None


def accessible_trip(user, trip_id):
    # Return the trip if the user owns it or is a member of it, otherwise None
    
    trip = db.session.get(Trip, trip_id)
    if trip is None:
        return None
    if trip.user_id == user.id or is_member(trip, user):
        return trip
    
    return None


def accessible_trips(user):
    # All trips the user owns or has joined, newest start date first

    joined_ids = db.select(TripMember.trip_id).filter_by(user_id = user.id)
    query = (db.select(Trip).where(db.or_(Trip.user_id == user.id, Trip.id.in_(joined_ids))).order_by(Trip.start_date.desc(), Trip.id.desc()))
    
    return db.session.execute(query).scalars().all()


def trip_for_user(trip, user):
    # The trip's normal JSON, plus who owns it and who it is shared with
    data = trip.to_dict()
    owner = db.session.get(User, trip.user_id)
    members = db.session.execute(db.select(User.id, User.name).join(TripMember, TripMember.user_id == User.id).filter(TripMember.trip_id == trip.id).order_by(TripMember.joined_at)).all()

    data["is_owner"] = trip.user_id == user.id

    if owner:
        data["owner_name"] = owner.name
    else:
        data["owner_name"] = None

    shared_with = []
    for member in members:
        shared_with.append(member.name)
    data["shared_with"] = shared_with

    # Only the owner needs member ids, so they can remove a specific person
    if data["is_owner"]:
        member_list = []
        for member in members:
            member_list.append({"id": member.id, "name": member.name})
        data["members"] = member_list

    return data


def remove_sharing(trip):
    # Delete the trip's members and share code. Call this before deleting the trip
    db.session.execute(db.delete(TripMember).filter_by(trip_id = trip.id))
    db.session.execute(db.delete(TripShareCode).filter_by(trip_id = trip.id))


# Routes

def current_user():
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return db.session.get(User, user_id)
    
    return None


def new_code():
    # Make a random code that no other trip is using
    while True:
        code = ""
        for _ in range(CODE_LENGTH):
            code += secrets.choice(CODE_ALPHABET)

        taken = db.session.execute(db.select(TripShareCode).filter_by(code = code)).scalar_one_or_none()
        if taken is None:
            return code


def clean_code(raw):
    # Accept 'k7q2-m9xd', 'K7Q2 M9XD' or 'K7Q2M9XD' and return 'K7Q2M9XD'
    if not isinstance(raw, str):
        return ""
    cleaned = ""
    for character in raw.upper():
        if character not in "- ":
            cleaned += character

    return cleaned


def show_code(code):
    # Show the code as two groups of four, for example K7Q2-M9XD
    return code[:4] + "-" + code[4:]


@sharing_api.post("/<int:trip_id>/share")
def share_trip(trip_id):
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    trip = accessible_trip(user, trip_id)
    if not trip:
        return jsonify(error = "Trip not found."), 404
    if trip.user_id != user.id:
        return jsonify(error = "Only the trip owner can share this trip."), 403

    # Reuse the trip's code if it already has one, so earlier codes keep working
    share = db.session.execute(db.select(TripShareCode).filter_by(trip_id = trip.id)).scalar_one_or_none()

    if share is None:
        share = TripShareCode(trip_id = trip.id, code = new_code())
        db.session.add(share)
        db.session.commit()

    return jsonify(code = show_code(share.code)), 200


@sharing_api.post("/join")
def join_trip():
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    data = request.get_json(silent = True) or {}
    code = clean_code(data.get("code"))

    if len(code) != CODE_LENGTH:
        return jsonify(error = "Enter the 8-character trip code."), 400

    share = db.session.execute(db.select(TripShareCode).filter_by(code = code)).scalar_one_or_none()
    if share is None:
        return jsonify(error = "No trip matches that code."), 404

    trip = db.session.get(Trip, share.trip_id)
    if trip is None:
        return jsonify(error = "No trip matches that code."), 404
    if trip.user_id == user.id:
        return jsonify(error = "This is already your trip."), 409
    if is_member(trip, user):
        return jsonify(error = "This trip is already in your trips."), 409

    db.session.add(TripMember(trip_id = trip.id, user_id = user.id))
    db.session.commit()

    return jsonify(trip = trip_for_user(trip, user)), 201


@sharing_api.post("/<int:trip_id>/leave")
def leave_trip(trip_id):
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    trip = accessible_trip(user, trip_id)
    if not trip:
        return jsonify(error = "Trip not found."), 404
    if trip.user_id == user.id:
        return jsonify(error = "You own this trip. Delete it instead of leaving."), 400

    db.session.execute(db.delete(TripMember).filter_by(trip_id = trip.id, user_id = user.id))
    db.session.commit()

    return jsonify(message = "You left the trip."), 200


@sharing_api.delete("/<int:trip_id>/members/<int:member_id>")
def remove_member(trip_id, member_id):
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    trip = accessible_trip(user, trip_id)
    if not trip:
        return jsonify(error = "Trip not found."), 404
    if trip.user_id != user.id:
        return jsonify(error = "Only the trip owner can remove people from this trip."), 403

    membership = db.session.execute(db.select(TripMember).filter_by(trip_id = trip.id, user_id = member_id)).scalar_one_or_none()
    if membership is None:
        return jsonify(error = "That person is not on this trip."), 404

    db.session.delete(membership)

    # Retire the old code so the removed person can't rejoin with it.
    # Everyone else stays on the trip, and the owner gets a new code the next time they share.
    db.session.execute(db.delete(TripShareCode).filter_by(trip_id = trip.id))
    db.session.commit()

    return jsonify(trip = trip_for_user(trip, user)), 200


@sharing_api.delete("/<int:trip_id>/share")
def stop_sharing(trip_id):
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    trip = accessible_trip(user, trip_id)
    if not trip:
        return jsonify(error = "Trip not found."), 404
    if trip.user_id != user.id:
        return jsonify(error = "Only the trip owner can stop sharing this trip."), 403

    # Removes every member and the code. The trip itself stays with the owner.
    remove_sharing(trip)
    db.session.commit()

    return jsonify(trip = trip_for_user(trip, user)), 200
