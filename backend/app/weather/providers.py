"""Server-side, cached Open-Meteo and OSRM adapters."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from urllib.parse import urlparse

import requests
from flask import current_app
from ..extensions import db
from .models import WeatherProviderCache, utcnow
from .rules import VARIABLES, numeric
from sqlalchemy.exc import IntegrityError


class ProviderError(Exception):
    pass


def save_cache(cached):
    # Independent trips can request the same coordinate at the same time.
    values = {"value": cached.value, "expires_at": cached.expires_at, "retry_at": cached.retry_at}
    key = cached.key
    try:
        db.session.add(cached)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        db.session.execute(db.update(WeatherProviderCache).where(WeatherProviderCache.key == key).values(**values))
        db.session.commit()


def cached_json(base, path, params, ttl):
    if urlparse(base).scheme != "https":
        raise ProviderError("Weather provider must use HTTPS.")
    url = base.rstrip("/") + path
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    now = utcnow()
    cached = db.session.get(WeatherProviderCache, key)
    if cached and cached.expires_at and cached.expires_at > now and cached.value is not None:
        return cached.value
    if cached and cached.retry_at and cached.retry_at > now:
        raise ProviderError("Provider temporarily unavailable; retry scheduled.")
    try:
        response = requests.get(url, params=params, timeout=(3, 15),
                                headers={"User-Agent": "AeroLink-Weather/1.0 (noncommercial travel prototype)"})
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict) or value.get("error"):
            raise ValueError("Invalid provider response")
    except (requests.RequestException, ValueError) as exc:
        retry_seconds = 300
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            try:
                retry_seconds = max(300, min(86400, int(exc.response.headers.get("Retry-After", "300"))))
            except ValueError:
                pass
        cached = cached or WeatherProviderCache(key=key)
        cached.retry_at = now + timedelta(seconds=retry_seconds)
        save_cache(cached)
        raise ProviderError("Provider request failed; previously retrieved forecasts are retained.") from exc
    cached = cached or WeatherProviderCache(key=key)
    value["_aerolink_retrieved_at"] = now.isoformat() + "Z"
    cached.value = value
    cached.expires_at = now + timedelta(seconds=ttl)
    cached.retry_at = None
    save_cache(cached)
    return value


def locations(query):
    raw = cached_json(current_app.config["WEATHER_GEOCODING_URL"], "/v1/search",
                      {"name": query, "count": 8, "language": "en", "format": "json"}, 86400)
    results = []
    items = raw.get("results") or []
    if not isinstance(items, list):
        raise ProviderError("Location search is unavailable.")
    for item in items:
        if not isinstance(item, dict):
            continue
        if not all(numeric(item.get(k)) for k in ("latitude", "longitude")) or not item.get("timezone"):
            continue
        results.append({"id": item.get("id"), "name": item.get("name", query),
                        "label": ", ".join(filter(None, [item.get("name"), item.get("admin1"), item.get("country")])),
                        "latitude": item["latitude"], "longitude": item["longitude"],
                        "timezone": item["timezone"]})
    return results


def forecast(location):
    raw = cached_json(current_app.config["WEATHER_FORECAST_URL"], "/v1/forecast", {
        "latitude": location["latitude"], "longitude": location["longitude"],
        "hourly": ",".join(VARIABLES), "forecast_days": 16, "timezone": "GMT",
        "timeformat": "unixtime", "temperature_unit": "celsius",
        "wind_speed_unit": "kmh", "precipitation_unit": "mm",
    }, current_app.config["WEATHER_CACHE_SECONDS"])
    hourly, units = raw.get("hourly", {}), raw.get("hourly_units", {})
    expected = {"temperature_2m": "°C", "precipitation_probability": "%", "rain": "mm", "snowfall": "cm",
                "weather_code": "wmo code", "visibility": "m", "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h"}
    if not isinstance(hourly, dict) or not isinstance(units, dict):
        raise ProviderError("Hourly forecast is unavailable.")
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise ProviderError("Hourly forecast is unavailable.")
    rows = []
    for index, stamp in enumerate(times):
        if not numeric(stamp):
            continue
        values = {}
        for key in VARIABLES:
            series = hourly.get(key, [])
            value = series[index] if isinstance(series, list) and index < len(series) else None
            # Reject unexpected provider units rather than scoring an incorrectly scaled value.
            values[key] = value if units.get(key) == expected[key] and numeric(value) else None
        rows.append({"time": datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z"),
                     "source_retrieved_at": raw.get("_aerolink_retrieved_at"), **values})
    if not rows:
        raise ProviderError("Hourly forecast is unavailable.")
    return rows


def sample_route(route):
    coords = route.get("geometry", {}).get("coordinates", [])
    durations = [d for leg in route.get("legs", []) for d in leg.get("annotation", {}).get("duration", [])]
    if (len(coords) < 2 or len(durations) != len(coords) - 1
            or not all(numeric(d) and d >= 0 for d in durations)
            or not all(isinstance(c, list) and len(c) >= 2 and numeric(c[0]) and numeric(c[1]) for c in coords)):
        raise ProviderError("Route timing details are unavailable.")
    total = sum(durations)
    count = min(25, max(2, math.ceil(total / 3600) + 1))
    samples, edge, cumulative = [], 0, 0.0
    for i in range(count):
        target = total * i / (count - 1)
        while edge < len(durations) - 1 and cumulative + durations[edge] < target:
            cumulative += durations[edge]
            edge += 1
        fraction = (target - cumulative) / durations[edge] if durations[edge] else 0
        a, b = coords[edge], coords[edge + 1]
        samples.append({"longitude": a[0] + (b[0] - a[0]) * fraction,
                        "latitude": a[1] + (b[1] - a[1]) * fraction, "offset_seconds": round(target)})
    samples[0].update(longitude=coords[0][0], latitude=coords[0][1])
    samples[-1].update(longitude=coords[-1][0], latitude=coords[-1][1])
    return {"duration_seconds": total, "distance_m": route.get("distance"), "samples": samples,
            "geometry": {"type": "LineString", "coordinates": coords}}


def driving_route(origin, destination):
    coordinates = f"{origin['longitude']},{origin['latitude']};{destination['longitude']},{destination['latitude']}"
    raw = cached_json(current_app.config["WEATHER_ROUTING_URL"], f"/route/v1/driving/{coordinates}",
                      {"overview": "full", "geometries": "geojson", "annotations": "duration", "alternatives": "false"}, 86400)
    if raw.get("code") != "Ok" or not raw.get("routes"):
        raise ProviderError("No driving route found between these locations.")
    return sample_route(raw["routes"][0])
