from datetime import datetime, timezone

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


class Flight(db.Model):
    #Latest known record for each flight. Alert checker compares new data against this

    __tablename__ = "flights"

    flight_number = db.Column(db.String(20), primary_key = True)

    #naive UTC
    scheduled_departure = db.Column(db.DateTime, nullable = False)
    estimated_departure = db.Column(db.DateTime, nullable = False)

    status = db.Column(db.String(20), nullable = False, default = "scheduled")
    gate = db.Column(db.String(10))
    last_updated = db.Column(db.DateTime, nullable = False, default = lambda: datetime.now(timezone.utc))


class Alert(db.Model):
    #An alert created by one of the flag rules

    __tablename__ = "alerts"
    __table_args__ = (db.UniqueConstraint("flight_number", "alert_type", "dedupe_key", name = "uq_alert_event"))

    id = db.Column(db.Integer, primary_key = True)
    flight_number = db.Column(db.String(20), nullable = False, index = True)
    alert_type = db.Column(db.String(30), nullable = False)
    message = db.Column(db.String(200), nullable = False)
    detail = db.Column(db.String(300))
    dedupe_key = db.Column(db.String(100), nullable = False)
    created_at = db.Column(db.DateTime, nullable = False, default = lambda: datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, nullable = False, default = False)

    def to_dict(self):
        return {"id": self.id, "flight_number": self.flight_number, "alert_type": self.alert_type, "message": self.message, "detail": self.detail, "created_at": self.created_at.isoformat() + "Z", "is_read": self.is_read}
