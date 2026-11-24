
from datetime import datetime, timezone

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from .extensions import db


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    title = db.Column(
        db.String(200),
        nullable=False,
    )

    done = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
            "created_at": self.created_at.isoformat(),
        }


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(100),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(
            password
        )

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password,
        )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }


class TravelPreference(db.Model):
    __tablename__ = "travel_preferences"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )

    destination = db.Column(
        db.String(200),
        nullable=True,
    )

    start_date = db.Column(
        db.Date,
        nullable=True,
    )

    end_date = db.Column(
        db.Date,
        nullable=True,
    )

    budget = db.Column(
        db.Float,
        nullable=True,
    )

    travelers = db.Column(
        db.Integer,
        default=1,
    )

    interests = db.Column(
        db.JSON,
        default=list,
    )

    cuisines = db.Column(
        db.JSON,
        default=list,
    )

    dietary_restrictions = db.Column(
        db.JSON,
        default=list,
    )

    accommodation_types = db.Column(
        db.JSON,
        default=list,
    )

    amenities = db.Column(
        db.JSON,
        default=list,
    )

    def to_dict(self):
        return {
            "destination": self.destination,
            "start_date": (
                self.start_date.isoformat()
                if self.start_date
                else None
            ),
            "end_date": (
                self.end_date.isoformat()
                if self.end_date
                else None
            ),
            "budget": self.budget,
            "travelers": self.travelers,
            "interests": self.interests or [],
            "cuisines": self.cuisines or [],
            "dietary_restrictions": (
                self.dietary_restrictions or []
            ),
            "accommodation_types": (
                self.accommodation_types or []
            ),
            "amenities": self.amenities or [],
        }


class Trip(db.Model):
    __tablename__ = "trips"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    destination = db.Column(
        db.String(200),
        nullable=False,
    )

    start_date = db.Column(
        db.Date,
        nullable=False,
    )

    end_date = db.Column(
        db.Date,
        nullable=False,
    )

    budget = db.Column(
        db.Float,
        nullable=True,
    )

    travelers = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    preference_snapshot = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    image_url = db.Column(
        db.String(1000),
        nullable=True,
    )

    image_credit = db.Column(
        db.JSON,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "destination": self.destination,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "budget": self.budget,
            "travelers": self.travelers,
            "preferences": self.preference_snapshot or {},
            "image_url": self.image_url,
            "image_credit": self.image_credit,
            "created_at": self.created_at.isoformat(),
        }


class SavedPlace(db.Model):
    __tablename__ = "saved_places"

    id = db.Column(db.Integer, primary_key=True)

    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    place_key = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    detail = db.Column(db.String(500), nullable=True)
    price = db.Column(db.String(100), nullable=True)
    image_url = db.Column(db.String(1000), nullable=True)
    why = db.Column(db.String(1000), nullable=True)
    place_metadata = db.Column(db.JSON, nullable=True)
    added_to_itinerary = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("0"))

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trip_id",
            "place_key",
            name="uq_saved_place_trip_key",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "place_key": self.place_key,
            "name": self.name,
            "category": self.category,
            "detail": self.detail,
            "price": self.price,
            "image": self.image_url,
            "why": self.why,
            "place_metadata": self.place_metadata or {},
            "added_to_itinerary": self.added_to_itinerary,
        }


class RecommendationFeedback(db.Model):
    __tablename__ = "recommendation_feedback"

    id = db.Column(db.Integer, primary_key=True)

    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    place_key = db.Column(
        db.String(100),
        nullable=False,
    )

    category = db.Column(
        db.String(30),
        nullable=False,
    )

    preference = db.Column(
        db.String(10),
        nullable=False,
    )

    place_categories = db.Column(
        db.JSON,
        nullable=False,
        default=list,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trip_id",
            "place_key",
            name="uq_feedback_trip_place",
        ),
    )

    def to_dict(self):
        return {
            "place_key": self.place_key,
            "category": self.category,
            "preference": self.preference,
            "place_categories": self.place_categories or [],
        }
