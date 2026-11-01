
from flask import Blueprint, jsonify, request, session
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import User

auth = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth.post("/register")
def register():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = data.get("password")

    if not name or not email or not isinstance(password, str):
        return jsonify(error="All fields are required."), 400

    if len(name) > 100 or len(email) > 255:
        return jsonify(error="Name or email is too long."), 400

    if len(password) < 10:
        return jsonify(error="Password must be at least 10 characters."), 400

    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return jsonify(error="Enter a valid email address."), 400

    if db.session.execute(
        db.select(User).filter_by(email=email)
    ).scalar_one_or_none():
        return jsonify(error="Email is already registered."), 409

    user = User(name=name, email=email)
    user.set_password(password)

    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Email is already registered."), 409

    session.clear()
    session["user_id"] = user.id

    return jsonify(user=user.to_dict()), 201


@auth.post("/login")
def login():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email") or "").strip().lower()
    password = data.get("password")

    if not email or not isinstance(password, str):
        return jsonify(error="Email and password are required."), 400

    user = db.session.execute(
        db.select(User).filter_by(email=email)
    ).scalar_one_or_none()

    if user is None or not user.check_password(password):
        return jsonify(error="Invalid email or password."), 401

    session.clear()
    session["user_id"] = user.id

    return jsonify(user=user.to_dict()), 200


@auth.get("/me")
def current_user():
    user_id = session.get("user_id")

    if user_id is None:
        return jsonify(error="Not authenticated."), 401

    user = db.session.get(User, user_id)

    if user is None:
        session.clear()
        return jsonify(error="Not authenticated."), 401

    return jsonify(user=user.to_dict()), 200


@auth.post("/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out successfully."), 200

@auth.post("/change-password")
def change_password():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id is not None else None
    if user is None:
        session.clear()
        return jsonify(error="Not authenticated."), 401

    data = request.get_json(silent=True) or {}
    current = data.get("current_password")
    new = data.get("new_password")
    if not isinstance(current, str) or not isinstance(new, str):
        return jsonify(error="Current and new passwords are required."), 400
    if not user.check_password(current):
        return jsonify(error="Current password is incorrect."), 400
    if len(new) < 10:
        return jsonify(error="New password must be at least 10 characters."), 400
    if len(new) > 256:
        return jsonify(error="New password is too long."), 400
    if current == new:
        return jsonify(error="Choose a password different from your current one."), 400

    user.set_password(new)
    db.session.commit()
    return jsonify(message="Password updated successfully."), 200


@auth.post("/delete-account")
def delete_account():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id is not None else None
    if user is None:
        session.clear()
        return jsonify(error="Not authenticated."), 401

    data = request.get_json(silent=True) or {}
    password = data.get("password")
    confirmation = data.get("confirmation")
    if not isinstance(password, str) or not user.check_password(password):
        return jsonify(error="Password is incorrect."), 400
    if confirmation != "DELETE":
        return jsonify(error="Type DELETE to confirm account deletion."), 400

    # Delete related preferences before the user to satisfy the existing FK.
    # When trip models are introduced, add explicit cleanup/cascades here too.
    from .models import TravelPreference
    db.session.query(TravelPreference).filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    session.clear()
    return jsonify(message="Account deleted successfully."), 200
