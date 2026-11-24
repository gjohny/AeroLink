#Live flight check: asks AirLabs about the flights on users' trips and feeds the answers to the alert checker.
#Nothing runs this automatically, so the AirLabs allowance is only used when someone runs it on purpose.

#Run from the backend folder (venv active, with AIRLABS_API_KEY and LIVE_FLIGHT_DATA=on in backend/.env):
#    python -m app.alerts.live_check                  check once
#    python -m app.alerts.live_check --every 10       keep checking every 10 minutes until Ctrl+C
#    python -m app.alerts.live_check --flight AA100   only check this flight number

#Which flights get checked: flights on any trip that depart yesterday, today, or tomorrow (by flight date).
#AirLabs only knows about a flight's current or next departure, so asking about a flight weeks away
#would waste a request and return a different day's flight.

#Each AirLabs answer is turned into the same record format the test data uses (see checker.py),
#so live data and test data go through the exact same rules and create the same kinds of alerts.

import argparse
import time
from datetime import date, datetime, timedelta

from config import Config

from ..extensions import db
from ..flights import FlightServiceError, _call_airlabs
from ..models import TripFlight
from .checker import ingest_flight

#Never check more often than this, to protect the allowance
MIN_MINUTES_BETWEEN_CHECKS = 5


class LiveDataError(Exception):
    pass


def fetch_airlabs_flight(flight_number, cfg = Config):
    #One request to AirLabs for one flight number, using Alan's AirLabs code in app/flights.py.
    #Returns the raw flight dict, or None if AirLabs has no such flight
    if not getattr(cfg, "LIVE_FLIGHT_DATA", False):
        raise LiveDataError("Live data is off. Set LIVE_FLIGHT_DATA=on in backend/.env to use AirLabs.")

    api_key = (getattr(cfg, "AIRLABS_API_KEY", "") or "").strip()
    if not api_key:
        raise LiveDataError("Add AIRLABS_API_KEY to backend/.env to use live flight data.")

    #3-letter airline codes (AAL100) are ICAO; 2-character codes (AA100) are IATA
    if len(flight_number) > 3 and flight_number[:3].isalpha():
        params = {"flight_icao": flight_number}
    else:
        params = {"flight_iata": flight_number}

    try:
        found = _call_airlabs("flight", params, api_key, float(getattr(cfg, "AIRLABS_TIMEOUT", 8)))
    except FlightServiceError as err:
        raise LiveDataError(str(err)) from None

    return found[0] if found else None


def _utc(value):
    #AirLabs UTC times look like "2026-11-20 14:10". Turn that into "2026-11-20T14:10:00Z"
    if not value:
        return None
    text = str(value).strip().replace(" ", "T")
    if len(text) == 16:
        text += ":00"
    return text + "Z"


def _plus_minutes(iso_time, minutes):
    moment = datetime.fromisoformat(iso_time.replace("Z", ""))
    return (moment + timedelta(minutes = minutes)).isoformat() + "Z"


def _best_time(raw, side, scheduled):
    #Actual time if it already happened, otherwise the estimate, otherwise scheduled plus the reported delay
    actual = _utc(raw.get(f"{side}_actual_utc"))
    if actual:
        return actual

    estimated = _utc(raw.get(f"{side}_estimated_utc"))
    if estimated:
        return estimated

    delay = raw.get(f"{side}_delayed")
    if scheduled and isinstance(delay, (int, float)) and delay > 0:
        return _plus_minutes(scheduled, delay)

    return scheduled


def airlabs_to_record(raw):
    #Convert one AirLabs flight into the checker's record format. Returns None if it's missing the basics
    flight_number = raw.get("flight_iata") or raw.get("flight_icao")
    scheduled_departure = _utc(raw.get("dep_time_utc"))
    if not flight_number or not scheduled_departure:
        return None

    scheduled_arrival = _utc(raw.get("arr_time_utc"))

    #The flight date is the LOCAL departure date ("2026-11-20 08:10" -> "2026-11-20"), matching what users type in
    local_departure = raw.get("dep_time") or raw.get("dep_time_utc")

    return {"flight_number": flight_number, "flight_date": str(local_departure)[:10], "airline": raw.get("airline_name") or raw.get("airline_iata"), "status": raw.get("status") or "scheduled", "departure_airport": raw.get("dep_iata"), "scheduled_departure": scheduled_departure, "estimated_departure": _best_time(raw, "dep", scheduled_departure), "departure_terminal": raw.get("dep_terminal"), "gate": raw.get("dep_gate"), "arrival_airport": raw.get("arr_iata"), "scheduled_arrival": scheduled_arrival, "estimated_arrival": _best_time(raw, "arr", scheduled_arrival) if scheduled_arrival else None, "arrival_terminal": raw.get("arr_terminal"), "arrival_gate": raw.get("arr_gate")}


def flights_to_check(today = None, only = None):
    #Unique (flight number, date) pairs on any trip, departing yesterday through tomorrow
    today = today or date.today()
    query = db.session.query(TripFlight.flight_number, TripFlight.flight_date).filter(TripFlight.flight_date >= today - timedelta(days = 1), TripFlight.flight_date <= today + timedelta(days = 1))
    if only:
        query = query.filter(TripFlight.flight_number == only.upper().replace(" ", ""))
    return query.distinct().order_by(TripFlight.flight_date, TripFlight.flight_number).all()


def check_once(cfg = Config, today = None, only = None, say = print):
    #Check each flight once. Returns how many AirLabs requests were used
    pairs = flights_to_check(today, only)
    if not pairs:
        say("No trip flights depart between yesterday and tomorrow, so there is nothing to check.")
        return 0

    requests_used = 0
    for flight_number, flight_date in pairs:
        raw = fetch_airlabs_flight(flight_number, cfg)
        requests_used += 1

        if raw is None:
            say(f"{flight_number} {flight_date}: AirLabs doesn't know this flight.")
            continue

        record = airlabs_to_record(raw)
        if record is None:
            say(f"{flight_number} {flight_date}: AirLabs didn't include a departure time, skipped.")
            continue

        #AirLabs answers with the flight's current or next departure, which may be a different day
        if record["flight_date"] != flight_date.isoformat():
            say(f"{flight_number} {flight_date}: AirLabs is showing the {record['flight_date']} departure instead, skipped.")
            continue

        #Use the number the user typed, so the record matches their trip even if AirLabs spells it differently
        record["flight_number"] = flight_number

        created = ingest_flight(record, cfg)
        if created:
            for alert in created:
                say(f"{flight_number} {flight_date}: NEW ALERT - {alert.message}")
        else:
            say(f"{flight_number} {flight_date}: updated ({record['status']}), no new alerts.")

    return requests_used


def main():
    parser = argparse.ArgumentParser(description = "Check trip flights against live AirLabs data.")
    parser.add_argument("--every", type = int, metavar = "MINUTES", help = f"keep checking every MINUTES minutes (at least {MIN_MINUTES_BETWEEN_CHECKS}) until Ctrl+C")
    parser.add_argument("--flight", metavar = "NUMBER", help = "only check this flight number")
    args = parser.parse_args()

    if args.every is not None and args.every < MIN_MINUTES_BETWEEN_CHECKS:
        parser.error(f"--every must be at least {MIN_MINUTES_BETWEEN_CHECKS} minutes to protect the AirLabs allowance")

    from app import create_app

    app = create_app()
    with app.app_context():
        total = 0
        try:
            while True:
                print(f"--- Live check at {datetime.now().strftime('%H:%M:%S')} ---")
                try:
                    total += check_once(only = args.flight)
                except LiveDataError as err:
                    print(f"Stopped: {err}")
                    break

                print(f"AirLabs requests used so far: {total}")
                if args.every is None:
                    break

                print(f"Next check in {args.every} minutes. Press Ctrl+C to stop.")
                time.sleep(args.every * 60)
        except KeyboardInterrupt:
            print(f"\nStopped. AirLabs requests used: {total}")


if __name__ == "__main__":
    main()
