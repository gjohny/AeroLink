#Flight Plan: the flights attached to a trip, their live status, and their alerts

#GET    /api/trips/<trip_id>/flights               the trip's flights with status, changes, and alert history (owner and members)
#POST   /api/trips/<trip_id>/flights               add a flight: {"flight_number", "flight_date", "departure_airport"?, "arrival_airport"?} (owner only)
#PUT    /api/trips/<trip_id>/flights/<flight_id>   swap a flight for a different one, same fields as POST (owner only)
#DELETE /api/trips/<trip_id>/flights/<flight_id>   remove a flight from the trip (owner only)

#Also has the helpers that decide which alerts a user can see: only alerts for flights on
#trips they own or were shared, which routes.py uses for the bell

import re

from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import Airport, Alert, AlertRead, Flight, Trip, TripFlight, TripMember, User
from ..trip_sharing import accessible_trip, current_user
from .checker import normalize_flight_number, parse_date

flight_plan_bp = Blueprint("flight_plan", __name__, url_prefix = "/api/trips")

#Two-character airline code (letters or digits, like AA, UA, B6), an optional third letter, then 1 to 4 digits
FLIGHT_NUMBER_PATTERN = re.compile(r"^[A-Z0-9]{2}[A-Z]?\d{1,4}[A-Z]?$")


#Helpers for which alerts a user can see

def accessible_trip_ids(user):
    #Ids of trips the user owns or has joined
    joined = db.select(TripMember.trip_id).filter_by(user_id = user.id)
    owned = db.select(Trip.id).filter_by(user_id = user.id)
    return db.union(owned, joined)


def visible_alerts_query(user):
    #Alerts for any flight on any of the user's trips, newest first
    trip_ids = accessible_trip_ids(user)
    flights_on_trips = db.select(TripFlight.flight_number, TripFlight.flight_date).where(TripFlight.trip_id.in_(trip_ids))
    return Alert.query.filter(db.tuple_(Alert.flight_number, Alert.flight_date).in_(flights_on_trips)).order_by(Alert.id.desc())


def read_alert_ids(user, alert_ids):
    #Which of these alerts this user has already read
    if not alert_ids:
        return set()
    rows = db.session.execute(db.select(AlertRead.alert_id).filter(AlertRead.user_id == user.id, AlertRead.alert_id.in_(alert_ids))).scalars().all()
    return set(rows)


def alert_for_user(alert, read_ids):
    data = alert.to_dict()
    data["is_read"] = alert.id in read_ids
    return data


def remove_trip_flights(trip):
    #Delete a trip's flights. Call this before deleting the trip
    db.session.execute(db.delete(TripFlight).filter_by(trip_id = trip.id))


#Building one flight card

def _iso(moment):
    if moment is None:
        return None
    return moment.isoformat() + "Z"


def _minutes_between(start, end):
    return int((end - start).total_seconds() // 60)


def _airport(code):
    #Name and city from Alan's airport table, when we have them
    if not code:
        return {"code": None, "name": None, "city": None}

    found = db.session.execute(db.select(Airport).filter_by(iata_code = code)).scalar_one_or_none()
    if found is None:
        return {"code": code, "name": None, "city": None}

    return {"code": code, "name": found.name, "city": found.municipality}


def _latest_alert(alerts, alert_type):
    #alerts are newest first
    for alert in alerts:
        if alert.alert_type == alert_type:
            return alert
    return None


def _changes(status, alerts):
    #What to highlight on the card. Each change is {type, old, new}, colored by type on the page
    changes = {"departure_time": None, "arrival_time": None, "departure_gate": None, "arrival_gate": None}
    if status is None:
        return changes

    threshold = current_app.config.get("DELAY_THRESHOLD_MINUTES", 20)

    if status.status != "cancelled":
        if _minutes_between(status.scheduled_departure, status.estimated_departure) >= threshold:
            changes["departure_time"] = {"type": "delay", "old": _iso(status.scheduled_departure), "new": _iso(status.estimated_departure)}

        if status.scheduled_arrival and status.estimated_arrival:
            if _minutes_between(status.scheduled_arrival, status.estimated_arrival) >= threshold:
                changes["arrival_time"] = {"type": "arrival_delay", "old": _iso(status.scheduled_arrival), "new": _iso(status.estimated_arrival)}

    #Only show a gate as changed if the latest gate alert still matches the current gate
    gate_alert = _latest_alert(alerts, "gate_change")
    if gate_alert and status.gate and gate_alert.new_value == status.gate:
        changes["departure_gate"] = {"type": "gate_change", "old": gate_alert.old_value, "new": gate_alert.new_value}

    arrival_gate_alert = _latest_alert(alerts, "arrival_gate_change")
    if arrival_gate_alert and status.arrival_gate and arrival_gate_alert.new_value == status.arrival_gate:
        changes["arrival_gate"] = {"type": "arrival_gate_change", "old": arrival_gate_alert.old_value, "new": arrival_gate_alert.new_value}

    return changes


def flight_entry(trip_flight, user):
    status = Flight.query.filter_by(flight_number = trip_flight.flight_number, flight_date = trip_flight.flight_date).first()
    alerts = Alert.query.filter_by(flight_number = trip_flight.flight_number, flight_date = trip_flight.flight_date).order_by(Alert.id.desc()).all()

    alert_ids = []
    for alert in alerts:
        alert_ids.append(alert.id)
    read_ids = read_alert_ids(user, alert_ids)

    alert_list = []
    for alert in alerts:
        alert_list.append(alert_for_user(alert, read_ids))

    #Live data wins over what the user typed, when it has a value
    departure_code = (status.departure_airport if status and status.departure_airport else trip_flight.departure_airport)
    arrival_code = (status.arrival_airport if status and status.arrival_airport else trip_flight.arrival_airport)

    departure = _airport(departure_code)
    arrival = _airport(arrival_code)

    if status:
        departure.update({"scheduled": _iso(status.scheduled_departure), "estimated": _iso(status.estimated_departure), "terminal": status.departure_terminal, "gate": status.gate})
        arrival.update({"scheduled": _iso(status.scheduled_arrival), "estimated": _iso(status.estimated_arrival), "terminal": status.arrival_terminal, "gate": status.arrival_gate})
    else:
        departure.update({"scheduled": None, "estimated": None, "terminal": None, "gate": None})
        arrival.update({"scheduled": None, "estimated": None, "terminal": None, "gate": None})

    return {"id": trip_flight.id, "flight_number": trip_flight.flight_number, "flight_date": trip_flight.flight_date.isoformat(), "airline": status.airline if status else None, "status": status.status if status else None, "has_live_data": status is not None, "last_updated": _iso(status.last_updated.replace(tzinfo = None)) if status else None, "departure": departure, "arrival": arrival, "changes": _changes(status, alerts), "alerts": alert_list, "entered": {"departure_airport": trip_flight.departure_airport, "arrival_airport": trip_flight.arrival_airport}}


#Reading and checking what the user typed

def _airport_code(data, key, label):
    raw = data.get(key)
    if raw is None or str(raw).strip() == "":
        return None

    code = str(raw).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(f"{label} airport should be a 3-letter code, like ORD.")

    #Only check against the airport table if it has been loaded (python scripts/import_airports.py)
    table_loaded = db.session.execute(db.select(Airport.id).limit(1)).first() is not None
    if table_loaded:
        found = db.session.execute(db.select(Airport.id).filter_by(iata_code = code)).first()
        if found is None:
            raise ValueError(f"We couldn't find an airport with the code {code}.")

    return code


def read_flight_form(data):
    #Returns (flight_number, flight_date, departure_airport, arrival_airport) or raises ValueError
    flight_number = normalize_flight_number(data.get("flight_number") or "")
    if not FLIGHT_NUMBER_PATTERN.match(flight_number):
        raise ValueError("Enter a flight number like AA100 or UA 2041.")

    if not data.get("flight_date"):
        raise ValueError("Choose the flight's departure date.")
    flight_date = parse_date(data["flight_date"])

    departure_airport = _airport_code(data, "departure_airport", "Departure")
    arrival_airport = _airport_code(data, "arrival_airport", "Arrival")

    if departure_airport and departure_airport == arrival_airport:
        raise ValueError("Departure and arrival airports can't be the same.")

    return flight_number, flight_date, departure_airport, arrival_airport


def _owner_trip(trip_id):
    #Returns (user, trip, error_response). Only the owner can change flights
    user = current_user()
    if not user:
        return None, None, (jsonify(error = "Not authenticated."), 401)

    trip = accessible_trip(user, trip_id)
    if not trip:
        return user, None, (jsonify(error = "Trip not found."), 404)

    if trip.user_id != user.id:
        return user, trip, (jsonify(error = "Only the trip owner can change flights."), 403)

    return user, trip, None


def _sorted_flights(trip):
    flights = TripFlight.query.filter_by(trip_id = trip.id).order_by(TripFlight.flight_date, TripFlight.id).all()
    return flights


#Routes

@flight_plan_bp.get("/<int:trip_id>/flights")
def list_trip_flights(trip_id):
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    trip = accessible_trip(user, trip_id)
    if not trip:
        return jsonify(error = "Trip not found."), 404

    owner = db.session.get(User, trip.user_id)

    flight_list = []
    for trip_flight in _sorted_flights(trip):
        flight_list.append(flight_entry(trip_flight, user))

    trip_info = {"id": trip.id, "destination": trip.destination, "start_date": trip.start_date.isoformat(), "end_date": trip.end_date.isoformat(), "is_owner": trip.user_id == user.id, "owner_name": owner.name if owner else None}

    return jsonify(trip = trip_info, flights = flight_list), 200


@flight_plan_bp.post("/<int:trip_id>/flights")
def add_trip_flight(trip_id):
    user, trip, error = _owner_trip(trip_id)
    if error:
        return error

    try:
        flight_number, flight_date, departure_airport, arrival_airport = read_flight_form(request.get_json(silent = True) or {})
    except ValueError as err:
        return jsonify(error = str(err)), 400

    already = TripFlight.query.filter_by(trip_id = trip.id, flight_number = flight_number, flight_date = flight_date).first()
    if already:
        return jsonify(error = "That flight is already on this trip."), 409

    trip_flight = TripFlight(trip_id = trip.id, flight_number = flight_number, flight_date = flight_date, departure_airport = departure_airport, arrival_airport = arrival_airport)
    db.session.add(trip_flight)
    db.session.commit()

    return jsonify(flight = flight_entry(trip_flight, user)), 201


@flight_plan_bp.put("/<int:trip_id>/flights/<int:flight_id>")
def swap_trip_flight(trip_id, flight_id):
    user, trip, error = _owner_trip(trip_id)
    if error:
        return error

    trip_flight = TripFlight.query.filter_by(id = flight_id, trip_id = trip.id).first()
    if trip_flight is None:
        return jsonify(error = "Flight not found."), 404

    try:
        flight_number, flight_date, departure_airport, arrival_airport = read_flight_form(request.get_json(silent = True) or {})
    except ValueError as err:
        return jsonify(error = str(err)), 400

    duplicate = TripFlight.query.filter(TripFlight.trip_id == trip.id, TripFlight.flight_number == flight_number, TripFlight.flight_date == flight_date, TripFlight.id != trip_flight.id).first()
    if duplicate:
        return jsonify(error = "That flight is already on this trip."), 409

    trip_flight.flight_number = flight_number
    trip_flight.flight_date = flight_date
    trip_flight.departure_airport = departure_airport
    trip_flight.arrival_airport = arrival_airport
    db.session.commit()

    return jsonify(flight = flight_entry(trip_flight, user)), 200


@flight_plan_bp.delete("/<int:trip_id>/flights/<int:flight_id>")
def remove_trip_flight(trip_id, flight_id):
    user, trip, error = _owner_trip(trip_id)
    if error:
        return error

    trip_flight = TripFlight.query.filter_by(id = flight_id, trip_id = trip.id).first()
    if trip_flight is None:
        return jsonify(error = "Flight not found."), 404

    db.session.delete(trip_flight)
    db.session.commit()

    return jsonify(message = "Flight removed."), 200
