#Make up an incident for a flight, for demos. It takes whatever is stored for the flight right now
#(from the live check or from test data), changes one thing, and sends it through the same checker
#as a real update. So the alerts it creates look exactly like real ones.

#Run from the backend folder (venv active):
#    python -m app.alerts.incident AA100 2026-12-01 gate            departure gate changes (or: gate C7)
#    python -m app.alerts.incident AA100 2026-12-01 delay           45 minute delay (or: delay 90)
#    python -m app.alerts.incident AA100 2026-12-01 arrival_gate    arrival gate changes (or: arrival_gate D2)
#    python -m app.alerts.incident AA100 2026-12-01 cancel          flight is cancelled
#    python -m app.alerts.incident AA100 2026-12-01 on_time         back to the original schedule (makes no alert)

#The flight needs data first. Either run the live check, or load test data:
#    python -m app.alerts.mock_data AA100 2026-12-01 on_time

import re
import sys
from datetime import timedelta

from config import Config

from ..models import Flight
from .checker import STORED_FIELDS, ingest_flight, normalize_flight_number, parse_date, parse_time

INCIDENTS = ("gate", "delay", "arrival_gate", "cancel", "on_time")


def _iso(moment):
    if moment is None:
        return None
    return moment.isoformat() + "Z"


def current_record(flight):
    #The stored flight, as a record in the checker's format
    record = {"flight_number": flight.flight_number, "flight_date": flight.flight_date.isoformat()}
    for field in STORED_FIELDS:
        value = getattr(flight, field)
        if hasattr(value, "isoformat"):
            value = _iso(value)
        record[field] = value
    return record


def next_gate(gate):
    #"B12" -> "B14". Something believable that is different from the current gate
    if not gate:
        return "A1"
    match = re.match(r"^([A-Za-z]*)(\d+)$", gate)
    if not match:
        return gate + "2"
    return f"{match.group(1)}{int(match.group(2)) + 2}"


def _later(iso_time, minutes):
    return _iso(parse_time(iso_time) + timedelta(minutes = minutes))


def make_incident(flight_number, flight_date, kind, value = None, cfg = Config):
    #Returns the list of new alerts. Raises ValueError with a readable message
    if kind not in INCIDENTS:
        raise ValueError(f"Unknown incident '{kind}'. Choose one of: {', '.join(INCIDENTS)}")

    flight_number = normalize_flight_number(flight_number)
    flight_date = parse_date(flight_date)

    flight = Flight.query.filter_by(flight_number = flight_number, flight_date = flight_date).first()
    if flight is None:
        raise ValueError(f"No data for {flight_number} on {flight_date} yet. Run the live check, or load test data first: python -m app.alerts.mock_data {flight_number} {flight_date} on_time")

    record = current_record(flight)

    if kind == "gate":
        record["gate"] = value or next_gate(record["gate"])

    elif kind == "arrival_gate":
        record["arrival_gate"] = value or next_gate(record["arrival_gate"])

    elif kind == "delay":
        minutes = int(value) if value else 45
        #Delays add up: a second "delay 30" makes the flight 30 minutes later than it already is
        record["estimated_departure"] = _later(record["estimated_departure"], minutes)
        if record.get("estimated_arrival"):
            record["estimated_arrival"] = _later(record["estimated_arrival"], minutes)
        if record["status"] == "scheduled":
            record["status"] = "delayed"

    elif kind == "cancel":
        record["status"] = "cancelled"

    elif kind == "on_time":
        record["estimated_departure"] = record["scheduled_departure"]
        record["estimated_arrival"] = record.get("scheduled_arrival")
        record["status"] = "scheduled"

    return ingest_flight(record, cfg)


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print("Usage: python -m app.alerts.incident FLIGHT_NUMBER YYYY-MM-DD gate|delay|arrival_gate|cancel|on_time [value]")
        sys.exit(1)

    from app import create_app

    app = create_app()
    with app.app_context():
        try:
            created = make_incident(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) == 5 else None)
        except ValueError as err:
            print(err)
            sys.exit(1)

        if created:
            for alert in created:
                print(f"NEW ALERT - {alert.message}")
        else:
            print("Updated the flight. No new alerts (nothing crossed an alert rule).")
