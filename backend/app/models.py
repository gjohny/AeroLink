from datetime import datetime, timezone

from werkzeug.security import (generate_password_hash, check_password_hash)

from .extensions import db


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
            "created_at": self.created_at.isoformat()
        }


class Flight(db.Model):
    #Latest known live record for each flight on a given date. Alert checker compares new data against this
    #The same flight number flies every day, so a flight is identified by its number AND its date

    __tablename__ = "flight_statuses"
    __table_args__ = (db.UniqueConstraint("flight_number", "flight_date", name = "uq_flight_status"),)

    id = db.Column(db.Integer, primary_key = True)
    flight_number = db.Column(db.String(20), nullable = False, index = True)
    flight_date = db.Column(db.Date, nullable = False)
    airline = db.Column(db.String(100))
    status = db.Column(db.String(20), nullable = False, default = "scheduled")

    #Departure side. Times are naive UTC
    departure_airport = db.Column(db.String(3))
    scheduled_departure = db.Column(db.DateTime, nullable = False)
    estimated_departure = db.Column(db.DateTime, nullable = False)
    departure_terminal = db.Column(db.String(10))
    gate = db.Column(db.String(10))  #departure gate

    #Arrival side. Times are naive UTC
    arrival_airport = db.Column(db.String(3))
    scheduled_arrival = db.Column(db.DateTime)
    estimated_arrival = db.Column(db.DateTime)
    arrival_terminal = db.Column(db.String(10))
    arrival_gate = db.Column(db.String(10))

    last_updated = db.Column(db.DateTime, nullable = False, default = lambda: datetime.now(timezone.utc))


class Alert(db.Model):
    #An alert created by one of the flag rules

    __tablename__ = "flight_alerts"
    __table_args__ = (db.UniqueConstraint("flight_number", "flight_date", "alert_type", "dedupe_key", name = "uq_alert_event"),)

    id = db.Column(db.Integer, primary_key = True)
    flight_number = db.Column(db.String(20), nullable = False, index = True)
    flight_date = db.Column(db.Date, nullable = False)
    alert_type = db.Column(db.String(30), nullable = False)
    message = db.Column(db.String(200), nullable = False)
    detail = db.Column(db.String(300))
    dedupe_key = db.Column(db.String(100), nullable = False)

    #What changed, so the Flight Plan page can show the old value crossed out
    old_value = db.Column(db.String(40))
    new_value = db.Column(db.String(40))

    created_at = db.Column(db.DateTime, nullable = False, default = lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "flight_number": self.flight_number, "flight_date": self.flight_date.isoformat(), "alert_type": self.alert_type, "message": self.message, "detail": self.detail, "old_value": self.old_value, "new_value": self.new_value, "created_at": self.created_at.isoformat() + "Z"}


class AlertRead(db.Model):
    #Marks an alert as read for one user. On a shared trip, each person has their own read state

    __tablename__ = "alert_reads"
    __table_args__ = (db.UniqueConstraint("alert_id", "user_id", name = "uq_alert_read"),)

    id = db.Column(db.Integer, primary_key = True)
    alert_id = db.Column(db.Integer, db.ForeignKey("flight_alerts.id"), nullable = False, index = True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable = False, index = True)


class TripFlight(db.Model):
    #A flight the trip owner added to a trip on the Flight Plan page

    __tablename__ = "trip_flights"
    __table_args__ = (db.UniqueConstraint("trip_id", "flight_number", "flight_date", name = "uq_trip_flight"),)

    id = db.Column(db.Integer, primary_key = True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable = False, index = True)
    flight_number = db.Column(db.String(20), nullable = False)
    flight_date = db.Column(db.Date, nullable = False)

    #Typed in by the user. Live data fills these in too once it arrives
    departure_airport = db.Column(db.String(3))
    arrival_airport = db.Column(db.String(3))

    created_at = db.Column(db.DateTime, nullable = False, default = lambda: datetime.now(timezone.utc))


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(db.String(255), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

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

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

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
            "amenities": self.amenities or []
        }


class Trip(db.Model):
    __tablename__ = "trips"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    destination = db.Column(db.String(200), nullable=False)

    start_date = db.Column(db.Date, nullable=False)

    end_date = db.Column(db.Date, nullable=False)

    budget = db.Column(db.Float, nullable=True)

    travelers = db.Column(db.Integer, nullable=False, default=1)

    preference_snapshot = db.Column(db.JSON, nullable=False, default=dict)

    image_url = db.Column(db.String(1000), nullable=True)

    image_credit = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

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
            "created_at": self.created_at.isoformat()
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


class Airport(db.Model):
    """Local OurAirports reference data; no live flight status or API routes yet.

    The primary key is the stable numeric ID from OurAirports. Keeping it means
    the data can be refreshed without changing an airport's local identity.
    """

    __tablename__ = "airports"
    __table_args__ = (db.Index("ix_airports_country_municipality", "iso_country", "municipality"),)

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


class TripMember(db.Model):
    #A user who joined someone else's trip with a share code

    __tablename__ = "trip_members"
    __table_args__ = (db.UniqueConstraint("trip_id", "user_id", name = "uq_trip_member"),)

    id = db.Column(db.Integer, primary_key = True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable = False, index = True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable = False, index = True)
    joined_at = db.Column(db.DateTime, nullable = False, default = lambda: datetime.now(timezone.utc))


class TripShareCode(db.Model):
    #The share code for a trip. Each trip has at most one code

    __tablename__ = "trip_share_codes"

    id = db.Column(db.Integer, primary_key = True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable = False, unique = True)
    code = db.Column(db.String(8), nullable = False, unique = True, index = True)
    created_at = db.Column(db.DateTime, nullable = False, default = lambda: datetime.now(timezone.utc))
