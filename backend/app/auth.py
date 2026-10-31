
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

    if len(password) < 12:
        return jsonify(error="Password must be at least 12 characters."), 400

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
