"""Additive weather tables: existing Trip/User schemas are unchanged."""
from datetime import datetime, timezone
from ..extensions import db


def utcnow():
    """Database timestamps are naive UTC; API timestamps include Z."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WeatherPlan(db.Model):
    __tablename__ = "weather_plans"
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), primary_key=True)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    routes = db.Column(db.JSON, nullable=False, default=dict)
    revision = db.Column(db.Integer, nullable=False, default=1)
    next_refresh_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    lease_until = db.Column(db.DateTime)
    lease_token = db.Column(db.String(36))
    last_attempt_at = db.Column(db.DateTime)
    last_error = db.Column(db.String(500))


class WeatherSnapshot(db.Model):
    __tablename__ = "weather_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class WeatherEvent(db.Model):
    __tablename__ = "weather_events"
    __table_args__ = (db.UniqueConstraint("trip_id", "dedupe_key", name="uq_weather_event"),)
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    detail = db.Column(db.JSON, nullable=False)
    dedupe_key = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    is_read = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {"id": self.id, "trip_id": self.trip_id, "revision": self.revision,
                "type": self.event_type, "severity": self.severity, "message": self.message,
                "detail": self.detail, "dedupe_key": self.dedupe_key,
                "created_at": self.created_at.isoformat() + "Z", "is_read": self.is_read}


class WeatherProviderCache(db.Model):
    __tablename__ = "weather_provider_cache"
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.JSON)
    expires_at = db.Column(db.DateTime)
    retry_at = db.Column(db.DateTime)


def delete_weather(trip_ids):
    """Also used by account deletion, which bulk-deletes trips."""
    for model in (WeatherEvent, WeatherSnapshot, WeatherPlan):
        db.session.execute(db.delete(model).where(model.trip_id.in_(trip_ids)))
