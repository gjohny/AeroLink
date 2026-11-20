#Compares an incoming flight record to the stored one, runs the rules, saves alerts

#This is the one place that reads and writes the flights and alerts tables. When Alan's data
#arrives, write a small adapter that turns his records into the dict shape below and call
#ingest_flight() on each one

#Flight record shape (times are ISO 8601; a trailing "Z" or offset is converted to UTC,
#and a time with no offset is treated as UTC):
#    {
#        "flight_number": "AA123",
#        "flight_date": "2026-11-02",           # optional: the local departure date. Defaults to the UTC date of scheduled_departure
#        "scheduled_departure": "2026-11-02T15:10:00Z",
#        "estimated_departure": "2026-11-02T15:10:00Z",
#        "status": "scheduled",                 # scheduled | delayed | cancelled | boarding | departed | landed ...
#
#        everything below is optional
#        "airline": "American Airlines",
#        "departure_airport": "ORD",            # IATA codes
#        "arrival_airport": "FCO",
#        "departure_terminal": "3",
#        "gate": "B12",                         # departure gate
#        "scheduled_arrival": "2026-11-03T06:30:00Z",
#        "estimated_arrival": "2026-11-03T06:30:00Z",
#        "arrival_terminal": "1",
#        "arrival_gate": "E4",
#    }

#The flight_date matters: a user adds "AA123 on Dec 1" to their trip, and only records with that
#number AND date show up on their Flight Plan page and in their alerts

from datetime import date, datetime, timezone

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


def parse_date(value):
    #Turn "2026-11-02" into a date
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise ValueError(f"'{value}' is not a valid date (use YYYY-MM-DD)") from None


def normalize_flight_number(value):
    #"aa 123" and "AA123" are the same flight
    cleaned = ""
    for character in str(value).upper():
        if character not in " -":
            cleaned += character
    return cleaned


def _text(record, key):
    #Optional text field: stripped string, or None when missing or blank
    value = record.get(key)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _time(record, key):
    #Optional time field
    if not record.get(key):
        return None
    return parse_time(record[key])


#Fields copied from the record onto the stored Flight row (everything except number and date)
STORED_FIELDS = ("airline", "status", "departure_airport", "scheduled_departure", "estimated_departure", "departure_terminal", "gate", "arrival_airport", "scheduled_arrival", "estimated_arrival", "arrival_terminal", "arrival_gate")


def _flight_to_dict(flight):
    old = {"flight_number": flight.flight_number, "flight_date": flight.flight_date}
    for field in STORED_FIELDS:
        old[field] = getattr(flight, field)
    return old


def ingest_flight(record, cfg = Config):
    #Store the record and return the list of newly created Alert objects
    missing = []
    for f in REQUIRED_FIELDS:
        if not record.get(f):
            missing.append(f)

    if missing:
        raise ValueError(f"Flight record is missing: {', '.join(missing)}")

    new = {"flight_number": normalize_flight_number(record["flight_number"]), "scheduled_departure": parse_time(record["scheduled_departure"]), "estimated_departure": parse_time(record["estimated_departure"]), "status": str(record["status"]).strip().lower()}

    if record.get("flight_date"):
        new["flight_date"] = parse_date(record["flight_date"])
    else:
        new["flight_date"] = new["scheduled_departure"].date()

    for key in ("airline", "departure_terminal", "gate", "arrival_terminal", "arrival_gate"):
        new[key] = _text(record, key)
    for key in ("departure_airport", "arrival_airport"):
        code = _text(record, key)
        new[key] = code.upper() if code else None
    for key in ("scheduled_arrival", "estimated_arrival"):
        new[key] = _time(record, key)

    flight = Flight.query.filter_by(flight_number = new["flight_number"], flight_date = new["flight_date"]).first()

    if flight:
        old = _flight_to_dict(flight)
    else:
        old = None

    created = []
    for found in run_rules(old, new, cfg):
        already = Alert.query.filter_by(flight_number = new["flight_number"], flight_date = new["flight_date"], alert_type = found["type"], dedupe_key = found["dedupe_key"]).first()
        if already:
            #Already told the user about this exact event
            continue
        alert = Alert(flight_number = new["flight_number"], flight_date = new["flight_date"], alert_type = found["type"], message = found["message"], detail = found["detail"], dedupe_key = found["dedupe_key"], old_value = found.get("old_value"), new_value = found.get("new_value"))
        db.session.add(alert)
        created.append(alert)

    if flight is None:
        flight = Flight(flight_number = new["flight_number"], flight_date = new["flight_date"])
        db.session.add(flight)

    for field in STORED_FIELDS:
        setattr(flight, field, new[field])
    flight.last_updated = datetime.now(timezone.utc)

    db.session.commit()
    return created
