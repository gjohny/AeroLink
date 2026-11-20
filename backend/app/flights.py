import re
import threading
import time

import requests
from flask import Blueprint, current_app, jsonify, request

from .airports import lookup_airports


flights_api = Blueprint("flights_api", __name__, url_prefix="/api")
AIRLABS_BASE = "https://airlabs.co/api/v9"
IATA = re.compile(r"^[A-Z]{3}$")
FLIGHT_IATA = re.compile(r"^[A-Z0-9]{2}[0-9]{1,5}[A-Z]?$", re.ASCII)
FLIGHT_ICAO = re.compile(r"^[A-Z]{3}[0-9]{1,5}[A-Z]?$", re.ASCII)

# Shared in-memory cache, one per backend process (not persisted to SQLite).
_cache = {}
_cache_lock = threading.Lock()


class FlightServiceError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not -100000 < number < 100000:
        return None
    return int(number) if number.is_integer() else number


def _airport_record(code_iata, code_icao, lookup):
    iata = (code_iata or "").strip().upper()
    icao = (code_icao or "").strip().upper()
    airport = lookup.get(iata) or lookup.get(icao)
    if airport:
        return airport
    return {
        "iata_code": iata or None, "icao_code": icao or None,
        "name": None, "city": None, "country": None, "region": None,
        "type": None, "latitude": None, "longitude": None,
        "scheduled_service": None,
    }


def normalize_flights(raw_flights, threshold=20):
    """Normalize provider records into a consistent JSON shape and attach alerts."""
    airport_codes = set()
    for raw in raw_flights:
        if isinstance(raw, dict):
            airport_codes.update(
                raw.get(key) for key in ("dep_iata", "dep_icao", "arr_iata", "arr_icao")
                if raw.get(key)
            )
    airports = lookup_airports(airport_codes)
    results = []
    for raw in raw_flights:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "unknown").strip().lower().replace("_", "-")
        if status in ("canceled", "cancelled"):
            status = "cancelled"
        dep_delay = _number(raw.get("dep_delayed"))
        arr_delay = _number(raw.get("arr_delayed"))
        if dep_delay is None and arr_delay is None:
            # A deprecated generic field sometimes exists on older API responses.
            dep_delay = _number(raw.get("delayed"))
        flight_code = raw.get("flight_iata") or raw.get("flight_icao") or raw.get("flight_number")
        alerts = []
        if status == "cancelled":
            alerts.append({"type": "cancelled", "severity": "high", "message": "Flight has been cancelled."})
        if dep_delay is not None and dep_delay >= threshold:
            alerts.append({"type": "delay", "severity": "warning", "phase": "departure",
                           "minutes": dep_delay, "message": f"Departure delayed by {dep_delay:g} minutes."})
        if arr_delay is not None and arr_delay >= threshold:
            alerts.append({"type": "delay", "severity": "warning", "phase": "arrival",
                           "minutes": arr_delay, "message": f"Arrival delayed by {arr_delay:g} minutes."})
        results.append({
            "flight_iata": raw.get("flight_iata"),
            "flight_icao": raw.get("flight_icao"),
            "flight_number": raw.get("flight_number"),
            "airline_iata": raw.get("airline_iata"),
            "status": status,
            "departure": {
                "airport": _airport_record(raw.get("dep_iata"), raw.get("dep_icao"), airports),
                "scheduled": raw.get("dep_time"),
                "estimated": raw.get("dep_estimated"),
                "actual": raw.get("dep_actual"),
                "delay_minutes": dep_delay,
                "terminal": raw.get("dep_terminal"), "gate": raw.get("dep_gate"),
            },
            "arrival": {
                "airport": _airport_record(raw.get("arr_iata"), raw.get("arr_icao"), airports),
                "scheduled": raw.get("arr_time"),
                "estimated": raw.get("arr_estimated"),
                "actual": raw.get("arr_actual"),
                "delay_minutes": arr_delay,
                "terminal": raw.get("arr_terminal"), "gate": raw.get("arr_gate"),
            },
            "position": {"latitude": _number(raw.get("lat")), "longitude": _number(raw.get("lng"))},
            "updated": raw.get("updated"),
            "alerts": alerts,
        })
    return results


def _call_airlabs(endpoint, params, api_key, timeout):
    """Only fixed endpoints; never log URLs, headers or the provider key."""
    try:
        response = requests.get(
            f"{AIRLABS_BASE}/{endpoint}",
            params={**params, "api_key": api_key}, timeout=timeout,
        )
    except requests.Timeout as exc:
        raise FlightServiceError("Flight service timed out. Try again shortly.", 504) from exc
    except requests.RequestException as exc:
        raise FlightServiceError("Flight service is temporarily unreachable.", 502) from exc

    # AirLabs sometimes uses 200 HTTP status with a structured API error.
    try:
        payload = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise FlightServiceError("Flight service returned an invalid response.") from exc
    if not isinstance(payload, dict):
        raise FlightServiceError("Flight service returned an unexpected response.")
    error = payload.get("error")
    if error:
        code = error.get("code") if isinstance(error, dict) else None
        if code in ("month_limit_exceeded", "minute_limit_exceeded", "hour_limit_exceeded"):
            raise FlightServiceError("AirLabs request allowance has been reached. Try later.", 429)
        if code in ("unknown_api_key", "expired_api_key"):
            raise FlightServiceError("AirLabs API key is invalid or expired. Update the backend .env.", 503)
        if code == "not_found":
            return []
        if code == "wrong_params":
            raise FlightServiceError("AirLabs rejected this flight query.", 400)
        raise FlightServiceError("AirLabs returned an error. Please try again.", 502)
    if response.status_code == 429:
        raise FlightServiceError("AirLabs is rate limiting requests. Try again later.", 429)
    if response.status_code in (401, 403):
        raise FlightServiceError("AirLabs authentication failed. Check the backend API key.", 503)
    if not response.ok:
        raise FlightServiceError("Flight service returned an HTTP error.", 502)
    data = payload.get("response")
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise FlightServiceError("Flight service returned an unexpected flight format.")


def _validated_query(args):
    allowed = {"flight_iata", "flight_icao", "dep_iata", "arr_iata", "mode", "limit"}
    unknown = set(args) - allowed
    if unknown:
        raise ValueError("Unsupported query parameter: " + ", ".join(sorted(unknown)))
    codes = {}
    for name, validator in (
        ("flight_iata", FLIGHT_IATA), ("flight_icao", FLIGHT_ICAO),
        ("dep_iata", IATA), ("arr_iata", IATA),
    ):
        value = (args.get(name) or "").strip().upper()
        if value and not validator.fullmatch(value):
            raise ValueError(f"Invalid {name} code.")
        if value:
            codes[name] = value
    if not codes:
        raise ValueError("Provide flight_iata, flight_icao, dep_iata or arr_iata.")
    if "flight_iata" in codes and "flight_icao" in codes:
        raise ValueError("Use either flight_iata or flight_icao, not both.")
    mode = (args.get("mode") or "auto").strip().lower()
    if mode not in ("auto", "live", "schedules"):
        raise ValueError("mode must be auto, schedules or live.")
    try:
        limit = int(args.get("limit", 30))
    except (ValueError, TypeError):
        raise ValueError("limit must be between 1 and 50.") from None
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50 (AirLabs free plan).")
    detailed = ("flight_iata" in codes or "flight_icao" in codes) and not (
        "dep_iata" in codes or "arr_iata" in codes
    )
    endpoint = "flight" if mode == "auto" and detailed else (
        "flights" if mode == "live" else "schedules"
    )
    # /flight accepts one flight number; /schedules and /flights accept airport filters.
    if endpoint == "flight":
        codes = {key: val for key, val in codes.items() if key.startswith("flight_")}
    if endpoint == "schedules":
        codes["limit"] = limit
    return endpoint, codes, limit


@flights_api.get("/flights")
def get_flights():
    try:
        endpoint, parameters, limit = _validated_query(request.args)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    api_key = (current_app.config.get("AIRLABS_API_KEY") or "").strip()
    if not api_key:
        return jsonify(error="Set AIRLABS_API_KEY in backend/.env to enable live flight data."), 503

    timeout = float(current_app.config.get("AIRLABS_TIMEOUT", 8))
    ttl = max(0, int(current_app.config.get("FLIGHT_CACHE_TTL_SECONDS", 300)))
    threshold = max(0, int(current_app.config.get("FLIGHT_DELAY_THRESHOLD_MINUTES", 20)))
    cache_key = (endpoint, tuple(sorted(parameters.items())), limit, threshold, api_key)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > now:
            result = cached[1]
        else:
            result = None
            if cached:
                _cache.pop(cache_key, None)
    was_cached = result is not None
    if result is None:
        try:
            raw = _call_airlabs(endpoint, parameters, api_key, timeout)
            records = normalize_flights(raw, threshold)[:limit]
        except FlightServiceError as exc:
            return jsonify(error=str(exc)), exc.status
        result = {"flights": records, "count": len(records), "source": f"airlabs/{endpoint}",
                  "delay_threshold_minutes": threshold}
        if ttl:
            with _cache_lock:
                # Prevent unbounded memory growth in long-running demo sessions.
                if len(_cache) >= 200:
                    _cache.clear()
                _cache[cache_key] = (time.monotonic() + ttl, result)
    return jsonify(**result, cached=was_cached)
