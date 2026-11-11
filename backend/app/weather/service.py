from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
import logging
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app
from sqlalchemy import or_
from ..extensions import db
from ..models import Trip
from . import providers
from .models import WeatherPlan, WeatherSnapshot, WeatherEvent, utcnow
from .rules import assess_hour, summarize, RANK, numeric
from .model_adapter import predict

LOG = logging.getLogger(__name__)
UTC = timezone.utc


def iso(moment):
    return moment.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if moment.tzinfo is None else moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def instant(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def location_value(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Select a location from the search results.")
    lat, lon = value.get("latitude"), value.get("longitude")
    label, zone = value.get("label"), value.get("timezone")
    if (not numeric(lat) or not -90 <= lat <= 90 or not numeric(lon) or not -180 <= lon <= 180
            or not isinstance(label, str) or not 1 <= len(label) <= 300 or not isinstance(zone, str)):
        raise ValueError("Select a valid location from the search results.")
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Location timezone is invalid.") from None
    return {"latitude": lat, "longitude": lon, "label": label, "timezone": zone}


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValueError("Send weather plan details.")
    destination = location_value(data.get("destination"))
    origin = location_value(data.get("origin"))
    mode = data.get("mode", "flight")
    if destination is None or mode not in ("flight", "driving"):
        raise ValueError("Select a destination and flight or driving travel mode.")
    if mode == "driving" and origin is None:
        raise ValueError("Select a departure location to generate a driving route.")
    result = {"origin": origin, "destination": destination, "mode": mode}
    for key in ("outbound_time", "return_time"):
        value = data.get(key)
        if value not in (None, ""):
            try:
                parsed = time.fromisoformat(value)
                if len(value) != 5 or parsed.tzinfo is not None:
                    raise ValueError()
            except (TypeError, ValueError):
                raise ValueError("Travel times must use HH:MM in the departure location's timezone.") from None
        result[key] = value or ("09:00" if mode == "driving" else None)
    return result


def latest_snapshot(plan):
    return db.session.execute(db.select(WeatherSnapshot).filter_by(trip_id=plan.trip_id, revision=plan.revision)
                              .order_by(WeatherSnapshot.id.desc()).limit(1)).scalar_one_or_none()


def ensure_plan(trip):
    plan = db.session.get(WeatherPlan, trip.id)
    if plan:
        return plan
    candidates = providers.locations(trip.destination)
    if len(candidates) != 1:
        return None
    destination = location_value(candidates[0])
    plan = WeatherPlan(trip_id=trip.id, settings={"destination": destination, "origin": None,
                       "mode": "flight", "outbound_time": None, "return_time": None})
    # Concurrent first visits can both resolve the same trip.
    from sqlalchemy.exc import IntegrityError
    try:
        db.session.add(plan)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        plan = db.session.get(WeatherPlan, trip.id)
    return plan


def local_window(day, location, departure_time=None):
    zone = ZoneInfo(location["timezone"])
    if departure_time:
        local = datetime.combine(day, time.fromisoformat(departure_time), zone)
        # Reject nonexistent spring-forward times; fall-back uses the first occurrence.
        if local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
            raise ValueError("Travel time does not exist in this timezone; choose another time.")
        start = local.astimezone(UTC)
        return start - timedelta(hours=2), start + timedelta(hours=3)
    start = datetime.combine(day, time.min, zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC)
    return start, end


def assess_forecast(location, start, end, hourly=None):
    """Alan's integration: coordinates/label/timezone plus aware scheduled UTC bounds.

    Returns hourly facts, hazard reasons, and a summary for the supplied window.
    Can be used for airports as well as cities. Never changes flight status.
    """
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("Supply an increasing timezone-aware forecast window.")
    hourly = providers.forecast(location) if hourly is None else hourly
    rows = []
    for row in hourly:
        if start <= instant(row["time"]) < end:
            assessed = assess_hour(row, current_app.config.get("WEATHER_THRESHOLDS"))
            rows.append({**row, **assessed})
    expected = max(1, int((end - start).total_seconds() / 3600))
    status = "available" if len(rows) >= expected and all(r["complete"] for r in rows) else "partial" if rows else "unavailable"
    return {"location": location, "start": iso(start), "end": iso(end), "status": status,
            "rows": rows, "retrieved_at": next((r.get("source_retrieved_at") for r in rows if r.get("source_retrieved_at")), None), "summary": summarize(rows), "coverage": {"expected_hours": expected, "available_hours": len(rows)},
            "reason": None if status == "available" else "Some requested hours or weather variables are outside available forecast coverage."}


def refresh_interval(trip, now):
    plan = db.session.get(WeatherPlan, trip.id)
    settings = plan.settings if plan else {}
    origin = settings.get("origin") or settings.get("destination")
    zone = ZoneInfo(origin["timezone"]) if origin else UTC
    # During the stay, the next travel day is the return day.
    start = datetime.combine(trip.start_date, time.min, zone).astimezone(UTC)
    end = datetime.combine(trip.end_date, time.min, zone).astimezone(UTC)
    target = start if start > now.replace(tzinfo=UTC) else end
    return timedelta(hours=1 if target - now.replace(tzinfo=UTC) <= timedelta(hours=72) else 6)


def monitoring_end(trip, settings):
    destination = settings["destination"]
    _, end = local_window(trip.end_date, destination)
    if settings.get("origin"):
        _, origin_end = local_window(trip.end_date, settings["origin"])
        end = max(end, origin_end)
    if settings.get("return_time"):
        _, departure_end = local_window(trip.end_date, destination, settings["return_time"])
        end = max(end, departure_end)
    route = None
    plan = db.session.get(WeatherPlan, trip.id)
    if plan:
        route = (plan.routes or {}).get("return", {})
    if settings.get("mode") == "driving" and route and route.get("duration_seconds"):
        departure = datetime.combine(trip.end_date, time.fromisoformat(settings.get("return_time") or "09:00"),
                                     ZoneInfo(destination["timezone"])).astimezone(UTC)
        end = max(end, departure + timedelta(seconds=route["duration_seconds"], hours=2))
    return end


def build_forecast(trip, plan, previous=None, now=None):
    now = now or datetime.now(UTC)
    settings = plan.settings
    destination, origin = settings["destination"], settings.get("origin")
    windows, hourly_cache, errors = [], {}, []
    routes = dict(plan.routes or {})

    def add(key, label, location, start, end, category, **extra):
        start = max(start, now.replace(minute=0, second=0, microsecond=0))
        if end <= start:
            return
        location_key = (round(location["latitude"], 5), round(location["longitude"], 5))
        base = {"key": key, "label": label, "category": category, **extra}
        try:
            if start > now + timedelta(days=16):
                result = {"location": location, "start": iso(start), "end": iso(end), "status": "unavailable", "rows": [],
                          "summary": summarize([]), "reason": "Travel dates are beyond the forecast horizon.", "coverage": {"available_hours": 0}}
            else:
                if location_key not in hourly_cache:
                    try:
                        hourly_cache[location_key] = providers.forecast(location)
                    except providers.ProviderError as exc:
                        hourly_cache[location_key] = exc
                hourly = hourly_cache[location_key]
                if isinstance(hourly, Exception):
                    raise hourly
                result = assess_forecast(location, start, end, hourly)
            windows.append({**base, **result, "fresh": True})
        except providers.ProviderError as exc:
            old = next((w for w in (previous or {}).get("windows", []) if w["key"] == key), None)
            if old:
                windows.append({**old, "status": "stale", "fresh": False, "reason": str(exc)})
            else:
                windows.append({**base, "location": location, "start": iso(start), "end": iso(end), "status": "unavailable", "fresh": False,
                                "rows": [], "summary": summarize([]), "coverage": {"available_hours": 0}, "reason": str(exc)})
            errors.append(str(exc))

    # Destination stay covers every local calendar day, including partial horizon coverage.
    stay_start, _ = local_window(trip.start_date, destination)
    _, stay_end = local_window(trip.end_date, destination)
    add("stay", "Destination stay", destination, stay_start, stay_end, "stay")
    for leg, day, departure, arrival in (("outbound", trip.start_date, origin, destination),
                                          ("return", trip.end_date, destination, origin)):
        travel_time = settings.get(f"{leg}_time")
        if settings["mode"] == "flight":
            for role, location in (("departure", departure), ("arrival", arrival)):
                if not location:
                    continue
                # Arrival time is unknown: keep the full local arrival day.
                start, end = local_window(day, location, travel_time if role == "departure" else None)
                add(f"{leg}_{role}", f"{leg.title()} {role}", location, start, end, "flight",
                    outlook="City-level outlook; scheduled airport arrival/departure windows are not yet linked.")
        elif departure and arrival:
            if leg not in routes or routes[leg].get("status") != "available":
                try:
                    routes[leg] = {**providers.driving_route(departure, arrival), "status": "available"}
                except providers.ProviderError as exc:
                    routes[leg] = {"status": "unavailable", "reason": str(exc)}
            route = routes[leg]
            moment = datetime.combine(day, time.fromisoformat(travel_time or "09:00"), ZoneInfo(departure["timezone"])).astimezone(UTC)
            if route["status"] == "available":
                for index, point in enumerate(route["samples"]):
                    eta = moment + timedelta(seconds=point["offset_seconds"])
                    location = {"latitude": point["latitude"], "longitude": point["longitude"],
                                "label": f"{leg.title()} route point {index + 1}", "timezone": departure["timezone"]}
                    start = eta.replace(minute=0, second=0, microsecond=0)
                    add(f"{leg}_route_{index}", location["label"], location, start, start + timedelta(hours=1), "driving",
                        eta=iso(eta), leg=leg)
            else:
                # Endpoints remain informative even if a route could not be generated.
                for role, location in (("departure", departure), ("arrival", arrival)):
                    start, end = local_window(day, location)
                    add(f"{leg}_{role}", f"{leg.title()} {role} (route unavailable)", location, start, end, "driving", leg=leg)
    flight = summarize([r for w in windows if w["category"] == "flight" for r in w["rows"]])
    driving = summarize([r for w in windows if w["category"] == "driving" for r in w["rows"]])
    for category, summary in (("flight", flight), ("driving", driving)):
        relevant = [w for w in windows if w["category"] == category]
        summary["complete"] = bool(relevant) and all(w["status"] == "available" for w in relevant) and summary["complete"]
    if settings["mode"] == "flight" and not origin:
        flight["complete"] = False
    if settings["mode"] == "driving" and any(routes.get(leg, {}).get("status") != "available" for leg in ("outbound", "return")):
        driving["complete"] = False
    model_rows = [r for w in windows if w["category"] == "flight" and w.get("fresh") for r in w["rows"]]
    model_row = max(model_rows, key=lambda r: r["score"] or 0, default={})
    model = predict(model_row, current_app.config.get("WEATHER_MODEL_MANIFEST"))
    if model["status"] == "available":
        model["assessed_hour"] = model_row.get("time")
        model["scope"] = "Highest rule-impact assessed flight hour; this is not a whole-trip probability."
    return {"windows": windows, "flight": flight, "driving": driving, "routes": routes,
            "model": model, "checked_at": iso(now), "retrieved_at": max((w.get("retrieved_at") for w in windows if w.get("retrieved_at")), default=iso(now) if any(w["rows"] for w in windows) else None), "source": "Open-Meteo", "errors": sorted(set(errors)),
            "mode": settings["mode"], "revision": plan.revision,
            "advisory": "Weather impact index, not a cancellation probability or confirmed flight delay."}


def changes(old, new, now):
    """Compare future, overlapping, complete facts only; stale/missing != improvement."""
    result = []
    before = {w["key"]: w for w in old.get("windows", [])}
    for window in new.get("windows", []):
        prior = before.get(window["key"])
        if not prior or not window.get("fresh"):
            continue
        if prior.get("location") != window.get("location"):
            continue
        previous = {r["time"]: r for r in prior["rows"] if r.get("complete") and instant(r["time"]) >= now}
        pairs = [(previous[r["time"]], r) for r in window["rows"] if r.get("complete") and r["time"] in previous]
        altered = []
        for a, b in pairs:
            hazards_a = {(h["type"], h["severity"]) for h in a["hazards"]}
            hazards_b = {(h["type"], h["severity"]) for h in b["hazards"]}
            if hazards_a != hazards_b or a["severity"] != b["severity"] or abs(a["score"] - b["score"]) >= 20:
                altered.append({"time": b["time"], "previous_score": a["score"], "score": b["score"],
                                "previous_severity": a["severity"], "severity": b["severity"],
                                "hazards": b["hazards"]})
        onset_shift = None
        highs_a = [instant(a["time"]) for a, b in pairs if a["severity"] == "high"]
        highs_b = [instant(b["time"]) for a, b in pairs if b["severity"] == "high"]
        if highs_a and highs_b and abs((min(highs_b) - min(highs_a)).total_seconds()) >= 10800:
            onset_shift = {"previous": iso(min(highs_a)), "current": iso(min(highs_b))}
        if altered or onset_shift:
            severity = max((a["severity"] for a in altered), key=RANK.get, default=window["summary"]["severity"])
            result.append({"type": "weather_change", "severity": severity,
                           "message": f"Weather forecast changed: {window['label']}",
                           "detail": {"window": window["key"], "location": window["location"], "changes": altered,
                                      "high_risk_onset_shift": onset_shift}})
    return result


def refresh_trip(trip_id, now=None):
    now = now or utcnow()
    trip, plan = db.session.get(Trip, trip_id), db.session.get(WeatherPlan, trip_id)
    if not trip or not plan or monitoring_end(trip, plan.settings) <= now.replace(tzinfo=UTC):
        return False
    token, revision = str(uuid.uuid4()), plan.revision
    claimed = db.session.execute(db.update(WeatherPlan).where(WeatherPlan.trip_id == trip_id,
              or_(WeatherPlan.lease_until.is_(None), WeatherPlan.lease_until < now))
              .values(lease_token=token, lease_until=now + timedelta(minutes=30), last_attempt_at=now))
    db.session.commit()
    if not claimed.rowcount:
        return False
    previous = latest_snapshot(plan)
    try:
        data = build_forecast(trip, plan, previous.data if previous else None, now.replace(tzinfo=UTC))
        # Provider requests commit caches. Re-read the lease/revision after their network waits.
        db.session.expire_all()
        plan = db.session.get(WeatherPlan, trip_id)
        if not plan or plan.lease_token != token:
            return False
        if plan.revision != revision:
            plan.lease_until = plan.lease_token = None
            db.session.commit()
            return False
        if any(w.get("fresh") for w in data["windows"]):
            snapshot = WeatherSnapshot(trip_id=trip_id, revision=revision, data=data, created_at=now)
            db.session.add(snapshot)
            for event in changes(previous.data, data, now.replace(tzinfo=UTC)) if previous else []:
                fingerprint = sha256(json.dumps([revision, previous.id, event], sort_keys=True).encode()).hexdigest()
                if not db.session.execute(db.select(WeatherEvent.id).filter_by(trip_id=trip_id, dedupe_key=fingerprint)).first():
                    db.session.add(WeatherEvent(trip_id=trip_id, revision=revision, event_type=event["type"],
                                               severity=event["severity"], message=event["message"], detail=event["detail"], dedupe_key=fingerprint))
        plan.routes = data["routes"]
        plan.last_error = "; ".join(data["errors"]) or None
        # An all-out-of-horizon attempt needs no snapshot, but remains scheduled.
        if not data["windows"]:
            plan.last_error = "No future travel windows remain."
        plan.next_refresh_at = now + refresh_interval(trip, now)
        plan.lease_until = plan.lease_token = None
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        LOG.exception("Weather refresh failed for trip %s", trip_id)
        db.session.execute(db.update(WeatherPlan).where(WeatherPlan.trip_id == trip_id, WeatherPlan.lease_token == token)
                           .values(lease_until=None, lease_token=None, last_error="Weather refresh failed; last forecast retained.",
                                   next_refresh_at=now + timedelta(minutes=15)))
        db.session.commit()
        return False


def weather_result(plan):
    snapshot = latest_snapshot(plan)
    data = snapshot.data if snapshot else None
    now = utcnow()
    stale = bool(data and (plan.last_error or now >= plan.next_refresh_at))
    coverage_status = "available"
    if data:
        statuses = [w["status"] for w in data["windows"]]
        coverage_status = "available" if statuses and all(s == "available" for s in statuses) else "partial" if any(w["rows"] for w in data["windows"]) else "unavailable"
        relevant = data["driving"] if data["mode"] == "driving" else data["flight"]
        if coverage_status == "available" and not relevant["complete"]:
            coverage_status = "partial"
    return {"status": "stale" if stale else coverage_status if data else "pending", "forecast": data,
            "revision": plan.revision, "snapshot_id": snapshot.id if snapshot else None,
            "last_error": plan.last_error, "last_attempt_at": iso(plan.last_attempt_at) if plan.last_attempt_at else None,
            "next_refresh_at": iso(plan.next_refresh_at), "refreshing": bool(plan.lease_until and plan.lease_until > now),
            "setup_required": not plan.settings.get("origin"),
            "monitoring_complete": monitoring_end(db.session.get(Trip, plan.trip_id), plan.settings) <= now.replace(tzinfo=UTC)}
