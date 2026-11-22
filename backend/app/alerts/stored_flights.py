#Flights saved in the database (from test data, the incident script, or an earlier live check).
#Used instead of AirLabs whenever LIVE_FLIGHT_DATA is off, so demos never touch the allowance.

#search_stored_flights   Alan's Flight Updates search (GET /api/flights), same result shape as his AirLabs results
#lookup_flight           the Look up button on the Flight Plan form (GET /api/flights/lookup)

from flask import Blueprint, current_app, jsonify, request

from ..airports import lookup_airports
from ..flights import FlightServiceError, _airport_record, _call_airlabs
from ..models import Flight
from ..trip_sharing import current_user
from .checker import normalize_flight_number, parse_date

lookup_bp = Blueprint("flight_lookup", __name__, url_prefix = "/api")


def _shown_time(moment):
    #Stored times are UTC, so say so on the page
    if moment is None:
        return None
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def _minutes_late(scheduled, estimated):
    if scheduled is None or estimated is None:
        return None
    return int((estimated - scheduled).total_seconds() // 60)


def stored_flight_to_result(flight, airports):
    #One saved flight in the same shape as Alan's normalize_flights() output
    return {"flight_iata": flight.flight_number, "flight_icao": None, "flight_number": flight.flight_number, "airline_iata": flight.airline, "status": flight.status.replace("_", "-"), "flight_date": flight.flight_date.isoformat(),
        "departure": {"airport": _airport_record(flight.departure_airport, None, airports), "scheduled": _shown_time(flight.scheduled_departure), "estimated": _shown_time(flight.estimated_departure), "actual": None, "delay_minutes": _minutes_late(flight.scheduled_departure, flight.estimated_departure), "terminal": flight.departure_terminal, "gate": flight.gate},
        "arrival": {"airport": _airport_record(flight.arrival_airport, None, airports), "scheduled": _shown_time(flight.scheduled_arrival), "estimated": _shown_time(flight.estimated_arrival), "actual": None, "delay_minutes": _minutes_late(flight.scheduled_arrival, flight.estimated_arrival), "terminal": flight.arrival_terminal, "gate": flight.arrival_gate},
        "position": {"latitude": None, "longitude": None}, "updated": _shown_time(flight.last_updated.replace(tzinfo = None)), "alerts": []}


def search_stored_flights(parameters, limit):
    #parameters come from Alan's _validated_query: flight_iata / flight_icao / dep_iata / arr_iata
    query = Flight.query
    number = parameters.get("flight_iata") or parameters.get("flight_icao")
    if number:
        query = query.filter(Flight.flight_number == normalize_flight_number(number))
    if parameters.get("dep_iata"):
        query = query.filter(Flight.departure_airport == parameters["dep_iata"])
    if parameters.get("arr_iata"):
        query = query.filter(Flight.arrival_airport == parameters["arr_iata"])

    flights = query.order_by(Flight.flight_date.desc(), Flight.scheduled_departure).limit(limit).all()

    codes = set()
    for flight in flights:
        for code in (flight.departure_airport, flight.arrival_airport):
            if code:
                codes.add(code)
    airports = lookup_airports(codes)

    results = []
    for flight in flights:
        results.append(stored_flight_to_result(flight, airports))
    return results


#Look up button

def _found(source, flight_number, flight_date, airline, departure_airport, arrival_airport, scheduled_departure, message):
    return {"found": True, "source": source, "flight_number": flight_number, "flight_date": flight_date, "airline": airline, "departure_airport": departure_airport, "arrival_airport": arrival_airport, "scheduled_departure": scheduled_departure, "message": message}


def _lookup_stored(flight_number, flight_date):
    exact = None
    if flight_date:
        exact = Flight.query.filter_by(flight_number = flight_number, flight_date = flight_date).first()

    flight = exact or Flight.query.filter_by(flight_number = flight_number).order_by(Flight.flight_date.desc()).first()
    if flight is None:
        hint = f" Load it with: python -m app.alerts.mock_data {flight_number} {flight_date.isoformat() if flight_date else 'YYYY-MM-DD'} on_time"
        return {"found": False, "source": "database", "message": f"{flight_number} isn't in the test data yet.{hint}"}

    if exact:
        message = f"Found {flight_number}."
    else:
        message = f"Found {flight_number} in the test data on {flight.flight_date.isoformat()}, not on the date you chose. Airports were filled in from that flight."

    return _found("database", flight.flight_number, flight.flight_date.isoformat(), flight.airline, flight.departure_airport, flight.arrival_airport, flight.scheduled_departure.isoformat() + "Z", message)


def _lookup_live(flight_number, flight_date):
    from .live_check import airlabs_to_record

    api_key = (current_app.config.get("AIRLABS_API_KEY") or "").strip()
    if not api_key:
        return None, ("Live data is on, but AIRLABS_API_KEY is missing from backend/.env.", 503)

    param = "flight_icao" if len(flight_number) > 3 and flight_number[:3].isalpha() else "flight_iata"
    try:
        raw = _call_airlabs("flight", {param: flight_number}, api_key, float(current_app.config.get("AIRLABS_TIMEOUT", 8)))
    except FlightServiceError as err:
        return None, (str(err), err.status)

    record = airlabs_to_record(raw[0]) if raw else None
    if record is None:
        return {"found": False, "source": "live", "message": f"AirLabs doesn't have a flight {flight_number} right now."}, None

    if flight_date and record["flight_date"] != flight_date.isoformat():
        message = f"AirLabs only shows {flight_number}'s next departure, on {record['flight_date']}. Airports were filled in from that flight."
    else:
        message = f"Found {flight_number}."

    return _found("live", flight_number, record["flight_date"], record["airline"], record["departure_airport"], record["arrival_airport"], record["scheduled_departure"], message), None


@lookup_bp.get("/flights/lookup")
def lookup_flight():
    #GET /api/flights/lookup?flight_number=AA100&flight_date=2026-12-01   (date optional)
    #Live data on: one AirLabs request. Off: looks in the saved flights (test data)
    if not current_user():
        return jsonify(error = "Not authenticated."), 401

    flight_number = normalize_flight_number(request.args.get("flight_number") or "")
    if not flight_number:
        return jsonify(error = "Enter a flight number to look up."), 400

    flight_date = None
    if request.args.get("flight_date"):
        try:
            flight_date = parse_date(request.args["flight_date"])
        except ValueError as err:
            return jsonify(error = str(err)), 400

    if current_app.config.get("LIVE_FLIGHT_DATA"):
        result, error = _lookup_live(flight_number, flight_date)
        if error:
            return jsonify(error = error[0]), error[1]
        return jsonify(result), 200

    return jsonify(_lookup_stored(flight_number, flight_date)), 200
