
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

class Airport(db.Model):
    """Local OurAirports reference data; no live flight status or API routes yet.

    The primary key is the stable numeric ID from OurAirports. Keeping it means
    the data can be refreshed without changing an airport's local identity.
    """

    __tablename__ = "airports"
    __table_args__ = (
        db.Index("ix_airports_country_municipality", "iso_country", "municipality"),
    )

    id = db.Column(db.Integer, primary_key=True)
    ident = db.Column(db.String(12), nullable=False)
    type = db.Column(db.String(32), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    municipality = db.Column(db.String(160), nullable=True)
    iso_country = db.Column(db.String(2), nullable=False, index=True)
    iso_region = db.Column(db.String(16), nullable=True)
    iata_code = db.Column(db.String(3), nullable=False, unique=True, index=True)
    icao_code = db.Column(db.String(4), nullable=True, index=True)
    latitude_deg = db.Column(db.Float, nullable=False)
    longitude_deg = db.Column(db.Float, nullable=False)
    scheduled_service = db.Column(db.Boolean, nullable=False, default=False)
