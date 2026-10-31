from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
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

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat()
        }


class TravelPreference(db.Model):
    __tablename__ = "travel_preferences"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    destination = db.Column(db.String(200), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    budget = db.Column(db.Float, nullable=True)
    travelers = db.Column(db.Integer, default=1)

    interests = db.Column(db.JSON, default=list)
    cuisines = db.Column(db.JSON, default=list)
    dietary_restrictions = db.Column(db.JSON, default=list)
    accommodation_types = db.Column(db.JSON, default=list)
    amenities = db.Column(db.JSON, default=list)

    def to_dict(self):
        return {
            "destination": self.destination,
            "start_date": (
                self.start_date.isoformat()
                if self.start_date else None
            ),
            "end_date": (
                self.end_date.isoformat()
                if self.end_date else None
            ),
            "budget": self.budget,
            "travelers": self.travelers,
            "interests": self.interests or [],
            "cuisines": self.cuisines or [],
            "dietary_restrictions": self.dietary_restrictions or [],
            "accommodation_types": self.accommodation_types or [],
            "amenities": self.amenities or [],
        }
