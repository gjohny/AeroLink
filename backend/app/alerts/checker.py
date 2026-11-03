#Compares an incoming flight record to the stored one, runs the rules, saves alerts

#This is the one place that reads and writes the flights and alerts tables. When Alan's data
#arrives, write a small adapter that turns his records into the dict shape below and call
#ingest_flight() on each one

#Flight record shape (times are ISO 8601; a trailing "Z" or offset is converted to UTC,
#and a time with no offset is treated as UTC):
#    {
#        "flight_number": "AA123",
#        "scheduled_departure": "2026-11-02T15:10:00Z",
#        "estimated_departure": "2026-11-02T15:10:00Z",
#        "status": "scheduled",   # scheduled | delayed | cancelled | departed ...
#        "gate": "B12",           # optional
#    }

from datetime import datetime, timezone

from config import Config

from ..extensions import db
from ..models import Alert, Flight
from .rules import run_rules

REQUIRED_FIELDS = ("flight_number", "scheduled_departure", "estimated_departure", "status")


def parse_time(value):
    #Turn an ISO 8601 string into a naive UTC datetime
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"'{value}' is not a valid ISO 8601 time") from None
    
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo = None)

    return moment


def _flight_to_dict(flight):
    return {"flight_number": flight.flight_number, "scheduled_departure": flight.scheduled_departure, "estimated_departure": flight.estimated_departure, "status": flight.status, "gate": flight.gate}


def ingest_flight(record, cfg = Config):
    #Store the record and return the list of newly created Alert objects
    missing = []
    for f in REQUIRED_FIELDS:
        if not record.get(f):
            missing.append(f)

    if missing:
        raise ValueError(f"Flight record is missing: {', '.join(missing)}")

    new = {"flight_number": str(record["flight_number"]).strip(), "scheduled_departure": parse_time(record["scheduled_departure"]), "estimated_departure": parse_time(record["estimated_departure"]), "status": str(record["status"]).strip().lower(), "gate": (str(record["gate"]).strip() if record.get("gate") else None)}

    flight = db.session.get(Flight, new["flight_number"])

    if flight:
        old = _flight_to_dict(flight)
    else:
        old = None

    created = []
    for found in run_rules(old, new, cfg):
        already = Alert.query.filter_by(flight_number = new["flight_number"], alert_type = found["type"], dedupe_key = found["dedupe_key"]).first()
        if already:
            #Already told the user about this exact event
            continue
        alert = Alert(flight_number = new["flight_number"], alert_type = found["type"], message = found["message"], detail = found["detail"], dedupe_key = found["dedupe_key"])
        db.session.add(alert)
        created.append(alert)

    if flight is None:
        flight = Flight(flight_number = new["flight_number"])
        db.session.add(flight)

    flight.scheduled_departure = new["scheduled_departure"]
    flight.estimated_departure = new["estimated_departure"]
    flight.status = new["status"]
    flight.gate = new["gate"]
    flight.last_updated = datetime.now(timezone.utc)

    db.session.commit()
    return created
