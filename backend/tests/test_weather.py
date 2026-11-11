"""Deterministic weather tests. All provider traffic is mocked."""
import copy
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

os.environ.setdefault("SECRET_KEY", "test-only-weather-key")
from app import create_app
from app.extensions import db
from app.models import User, Trip
from app.weather.models import WeatherPlan, WeatherSnapshot, WeatherEvent
from app.weather.providers import forecast, sample_route, cached_json, ProviderError
from app.weather.rules import assess_hour, summarize
from app.weather.service import (validate_settings, local_window, build_forecast, changes,
    refresh_trip, refresh_interval, latest_snapshot, weather_result, iso, monitoring_end, assess_forecast)
from app.weather import check_due
from app.weather.model_adapter import predict

UTC = timezone.utc
DALLAS = {"label": "Dallas, Texas", "latitude": 32.78, "longitude": -96.8, "timezone": "America/Chicago"}
DENVER = {"label": "Denver, Colorado", "latitude": 39.74, "longitude": -104.99, "timezone": "America/Denver"}
CLEAR = {"temperature_2m": 12, "precipitation_probability": 0, "rain": 0, "snowfall": 0,
    "weather_code": 0, "visibility": 15000, "wind_speed_10m": 10, "wind_gusts_10m": 15}


def hourly(start, count=96, **values):
    return [{"time": iso(start + timedelta(hours=i)), **CLEAR, **values} for i in range(count)]


def window(rows):
    rows = [{**r, **assess_hour(r)} for r in rows]
    return {"key": "stay", "label": "Stay", "location": DENVER, "fresh": True, "rows": rows, "summary": summarize(rows)}


class RulesTests(unittest.TestCase):
    def test_boundaries(self):
        cases = [("rain", 2.49, "low"), ("rain", 2.5, "moderate"), ("rain", 7.5, "high"),
            ("snowfall", 0.01, "moderate"), ("snowfall", 1, "high"), ("visibility", 5000, "low"),
            ("visibility", 4999, "moderate"), ("visibility", 1000, "moderate"), ("visibility", 999, "high"),
            ("wind_speed_10m", 35, "moderate"), ("wind_speed_10m", 50, "high"), ("wind_gusts_10m", 70, "high")]
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                self.assertEqual(assess_hour({**CLEAR, key: value})["severity"], expected)

    def test_codes_combination_missing_and_configuration(self):
        self.assertEqual(assess_hour({**CLEAR, "weather_code": 95})["score"], 40)
        self.assertEqual(assess_hour({**CLEAR, "weather_code": 66})["severity"], "high")
        self.assertEqual(assess_hour({**CLEAR, "weather_code": 95, "rain": 10, "snowfall": 2, "visibility": 100})["score"], 100)
        result = assess_hour({**CLEAR, "rain": 10, "weather_code": 65, "wind_speed_10m": 60, "wind_gusts_10m": 90})
        self.assertEqual(result["score"], 70); self.assertEqual(len(result["hazards"]), 2)
        self.assertIsNone(assess_hour({})["score"])
        self.assertEqual(assess_hour({})["severity"], "unknown")
        self.assertFalse(assess_hour({**CLEAR, "visibility": None})["complete"])
        self.assertIn("rain", assess_hour({**CLEAR, "rain": float("nan")})["missing_variables"])
        self.assertEqual(assess_hour({**CLEAR, "rain": 3}, {"rain_moderate": 4})["score"], 0)
        self.assertEqual(summarize([assess_hour(CLEAR), assess_hour({**CLEAR, "weather_code": 95})])["score"], 40)


class WeatherTests(unittest.TestCase):
    def setUp(self):
        class Config:
            TESTING = True
            SECRET_KEY = "test-weather-key"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            CORS_ORIGINS = ["http://localhost"]
            WEATHER_FORECAST_URL = "https://weather.test"
            WEATHER_GEOCODING_URL = "https://geocoding.test"
            WEATHER_ROUTING_URL = "https://routing.test"
            WEATHER_CACHE_SECONDS = 1800
            WEATHER_WORKER_INTERVAL_SECONDS = 300
            WEATHER_MODEL_MANIFEST = None
        self.app = create_app(Config)
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()
        self.now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        self.day = self.now.date() + timedelta(days=1)
        user = User(name="Nihal", email="nihal@example.test"); user.set_password("test-password-123")
        db.session.add(user); db.session.flush(); self.user_id = user.id
        self.trip = Trip(user_id=user.id, destination="Denver", start_date=self.day, end_date=self.day + timedelta(days=1))
        db.session.add(self.trip); db.session.commit(); self.trip_id = self.trip.id
        with self.client.session_transaction() as session: session["user_id"] = self.user_id
        self.settings = {"origin": DALLAS, "destination": DENVER, "mode": "flight", "outbound_time": None, "return_time": None}
        self.network = patch("app.weather.providers.requests.get", side_effect=AssertionError("Unexpected live request"))
        self.network.start()

    def tearDown(self):
        self.network.stop(); db.session.remove(); db.drop_all(); self.ctx.pop()

    def plan(self, **settings):
        plan = WeatherPlan(trip_id=self.trip_id, settings={**self.settings, **settings})
        db.session.add(plan); db.session.commit(); return plan

    def test_authenticated_owned_routes(self):
        client = self.app.test_client(); base = f"/api/trips/{self.trip_id}"
        paths = [("get", "/weather"), ("get", "/weather-plan"), ("put", "/weather-plan"),
            ("post", "/weather/refresh"), ("get", "/weather/events"), ("post", "/weather/events/1/read")]
        for method, path in paths:
            self.assertEqual(getattr(client, method)(base + path, json={}).status_code, 401)
        self.assertEqual(client.get("/api/weather/locations?q=Dallas").status_code, 401)
        other = User(name="Other", email="other@example.test", password_hash="unused")
        db.session.add(other); db.session.commit()
        with client.session_transaction() as session: session["user_id"] = other.id
        for method, path in paths:
            self.assertEqual(getattr(client, method)(base + path, json={}).status_code, 404)

    def test_plan_validation_revision_search_existing_trip(self):
        base = f"/api/trips/{self.trip_id}"
        self.assertIsNone(self.client.get(base + "/weather-plan").json["plan"])
        for bad in ([], {**self.settings, "mode": "boat"}, {**self.settings, "origin": {**DALLAS, "latitude": True}},
            {**self.settings, "outbound_time": "garbage"}, {**self.settings, "destination": {**DENVER, "timezone": "Fake/Zone"}}):
            self.assertEqual(self.client.put(base + "/weather-plan", json=bad).status_code, 400)
        result = self.client.put(base + "/weather-plan", json=self.settings)
        self.assertEqual(result.status_code, 200); self.assertEqual(result.json["revision"], 1)
        self.assertEqual(self.client.put(base + "/weather-plan", json={**self.settings, "mode": "driving"}).json["revision"], 2)
        self.assertEqual(db.session.get(Trip, self.trip_id).destination, "Denver")
        self.assertEqual(self.client.get("/api/weather/locations?q=x").status_code, 400)
        with patch("app.weather.providers.locations", return_value=[DALLAS, DENVER]):
            self.assertEqual(len(self.client.get("/api/weather/locations?q=city").json["locations"]), 2)

    def test_trip_autocomplete_selection_initializes_weather(self):
        payload = {"destination": DENVER["label"], "start_date": self.day.isoformat(),
                   "end_date": (self.day + timedelta(days=2)).isoformat(), "destination_location": DENVER}
        with patch("app.trips.find_destination_photo", return_value=None):
            response = self.client.post("/api/trips", json=payload)
        self.assertEqual(response.status_code, 201)
        trip_id = response.json["trip"]["id"]
        saved = db.session.get(WeatherPlan, trip_id)
        self.assertEqual(saved.settings["destination"], DENVER)
        self.assertIsNone(saved.settings["origin"])
        self.assertEqual(saved.settings["mode"], "flight")

    def test_custom_destination_and_invalid_selection(self):
        payload = {"destination": "Somewhere special", "start_date": self.day.isoformat(),
                   "end_date": self.day.isoformat()}
        with patch("app.trips.find_destination_photo", return_value=None):
            response = self.client.post("/api/trips", json=payload)
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(db.session.get(WeatherPlan, response.json["trip"]["id"]))
        with patch("app.trips.find_destination_photo") as photo:
            invalid = self.client.post("/api/trips", json={**payload, "destination_location": {**DENVER, "latitude": 999}})
        self.assertEqual(invalid.status_code, 400)
        photo.assert_not_called()

    def test_unique_destination_ambiguity(self):
        with patch("app.weather.providers.locations", return_value=[DALLAS, DENVER]):
            self.assertEqual(self.client.get(f"/api/trips/{self.trip_id}/weather").json["status"], "setup_required")
            self.assertIsNone(db.session.get(WeatherPlan, self.trip_id))
        with patch("app.weather.providers.locations", return_value=[DENVER]):
            result = self.client.get(f"/api/trips/{self.trip_id}/weather").json
            self.assertTrue(result["setup_required"]); self.assertEqual(result["status"], "pending")
            self.assertIsNotNone(db.session.get(WeatherPlan, self.trip_id))

    def test_timezone_dst_and_default_times(self):
        a, b = local_window(date(2027, 3, 14), DALLAS)
        self.assertEqual((b-a).total_seconds(), 23*3600)
        a, b = local_window(date(2027, 11, 7), DALLAS)
        self.assertEqual((b-a).total_seconds(), 25*3600)
        with self.assertRaises(ValueError): local_window(date(2027, 3, 14), DALLAS, "02:30")
        self.assertEqual(validate_settings({**self.settings, "mode": "driving"})["outbound_time"], "09:00")

    def test_provider_units_and_missing(self):
        response = {"hourly": {"time": [self.now.timestamp()], **{key: [value] for key, value in CLEAR.items()}},
            "hourly_units": {"temperature_2m": "°C", "precipitation_probability": "%", "rain": "mm", "snowfall": "cm",
                "weather_code": "wmo code", "visibility": "m", "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h"}}
        with patch("app.weather.providers.cached_json", return_value=response):
            self.assertEqual(forecast(DALLAS)[0]["temperature_2m"], 12)
            response["hourly_units"]["rain"] = "inch"
            self.assertIsNone(forecast(DALLAS)[0]["rain"])
            response["hourly"]["snowfall"] = []
            self.assertIsNone(forecast(DALLAS)[0]["snowfall"])

    def test_cache_and_backoff(self):
        with patch("app.weather.providers.requests.get") as get:
            get.return_value = Mock(json=lambda: {"ok": True}, raise_for_status=lambda: None)
            self.assertTrue(cached_json("https://test", "/x", {}, 100)["ok"])
            cached_json("https://test", "/x", {}, 100); self.assertEqual(get.call_count, 1)
            import requests
            get.side_effect = requests.Timeout()
            with self.assertRaises(ProviderError): cached_json("https://test", "/bad", {}, 100)
            with self.assertRaises(ProviderError): cached_json("https://test", "/bad", {}, 100)
            self.assertEqual(get.call_count, 2)
        with self.assertRaises(ProviderError): cached_json("http://test", "/x", {}, 100)

    def test_road_sampling_and_cap(self):
        route = {"geometry": {"coordinates": [[0, 0], [0, 1], [1, 1]]}, "legs": [{"annotation": {"duration": [3600, 3600]}}], "distance": 5000}
        result = sample_route(route)
        self.assertEqual(len(result["samples"]), 3)
        self.assertEqual(result["samples"][1]["longitude"], 0)
        self.assertEqual(result["samples"][1]["latitude"], 1)
        self.assertEqual(result["samples"][-1]["offset_seconds"], 7200)
        route["legs"][0]["annotation"]["duration"] = [100000, 100000]
        self.assertEqual(len(sample_route(route)["samples"]), 25)
        route["legs"] = []
        with self.assertRaises(ProviderError): sample_route(route)

    def test_return_and_forecast_horizon(self):
        plan = self.plan()
        # Anchor partial coverage to the travel window, not the wall-clock hour.
        # Near midnight, 30 hours starting "now" may end before the trip begins.
        coverage_start, _ = local_window(self.trip.start_date, DENVER)
        with patch("app.weather.providers.forecast", return_value=hourly(coverage_start, 30)):
            result = build_forecast(self.trip, plan, now=self.now)
        self.assertEqual({w["key"] for w in result["windows"]}, {"stay", "outbound_departure", "outbound_arrival", "return_departure", "return_arrival"})
        self.assertTrue(any(w["status"] == "partial" for w in result["windows"]))
        self.assertEqual(result["model"]["status"], "unavailable")
        self.trip.start_date += timedelta(days=50); self.trip.end_date += timedelta(days=50)
        with patch("app.weather.providers.forecast") as fetch:
            result = build_forecast(self.trip, plan, now=self.now); fetch.assert_not_called()
        self.assertTrue(all(w["status"] == "unavailable" for w in result["windows"]))
        self.assertIsNone(result["flight"]["score"])

    def test_midroute_hazard_and_return_direction(self):
        plan = self.plan(mode="driving", outbound_time="09:00", return_time="09:00")
        route = {"duration_seconds": 7200, "distance_m": 10000, "samples": [
            {"latitude": 32, "longitude": -96, "offset_seconds": 0}, {"latitude": 35, "longitude": -100, "offset_seconds": 3600},
            {"latitude": 39, "longitude": -104, "offset_seconds": 7200}]}
        def fetch(location): return hourly(self.now, 100, weather_code=95 if location["latitude"] == 35 else 0)
        with patch("app.weather.providers.driving_route", return_value=route) as router, patch("app.weather.providers.forecast", side_effect=fetch):
            result = build_forecast(self.trip, plan, now=self.now)
        self.assertEqual(router.call_count, 2); self.assertEqual(router.call_args_list[1].args, (DENVER, DALLAS))
        self.assertEqual(result["driving"]["severity"], "high")
        self.assertEqual(len([w for w in result["windows"] if w["category"] == "driving"]), 6)

    def test_route_failure_keeps_endpoints(self):
        plan = self.plan(mode="driving", outbound_time="09:00", return_time="09:00")
        with patch("app.weather.providers.driving_route", side_effect=ProviderError("No route")), patch("app.weather.providers.forecast", return_value=hourly(self.now, 100)):
            result = build_forecast(self.trip, plan, now=self.now)
        self.assertEqual(result["routes"]["outbound"]["status"], "unavailable"); self.assertEqual(len(result["windows"]), 5)
        self.assertFalse(result["driving"]["complete"])

    def test_meaningful_changes_ignore_missing_stale_past_new_hours(self):
        old = {"windows": [window(hourly(self.now, 6))]}
        new = {"windows": [window(hourly(self.now, 6, weather_code=95))]}
        self.assertEqual(len(changes(old, new, self.now)), 1)
        self.assertEqual(changes(new, old, self.now)[0]["severity"], "low")
        self.assertEqual(changes(new, {"windows": [window(hourly(self.now, 6, visibility=None))]}, self.now), [])
        new["windows"][0]["fresh"] = False; self.assertEqual(changes(old, new, self.now), [])
        new["windows"][0]["fresh"] = True; self.assertEqual(changes(old, new, self.now + timedelta(days=10)), [])
        self.assertEqual(changes(old, {"windows": [window(hourly(self.now + timedelta(days=1), 6, weather_code=95))]}, self.now), [])

    def test_high_onset_shift(self):
        first = hourly(self.now, 10); second = copy.deepcopy(first)
        for row in first[1:3]: row["weather_code"] = 95
        for row in second[5:7]: row["weather_code"] = 95
        result = changes({"windows": [window(first)]}, {"windows": [window(second)]}, self.now)
        self.assertIsNotNone(result[0]["detail"]["high_risk_onset_shift"])

    def test_refresh_baseline_dedup_and_failure_retention(self):
        plan = self.plan()
        with patch("app.weather.providers.forecast", return_value=hourly(self.now, 100)):
            self.assertTrue(refresh_trip(self.trip_id, self.now.replace(tzinfo=None)))
        self.assertEqual(db.session.query(WeatherEvent).count(), 0)
        with patch("app.weather.providers.forecast", return_value=hourly(self.now, 100, weather_code=95)):
            refresh_trip(self.trip_id, self.now.replace(tzinfo=None) + timedelta(minutes=10))
            count = db.session.query(WeatherEvent).count(); self.assertGreater(count, 0)
            refresh_trip(self.trip_id, self.now.replace(tzinfo=None) + timedelta(minutes=20))
            self.assertEqual(db.session.query(WeatherEvent).count(), count)
        snapshot = latest_snapshot(plan)
        with patch("app.weather.providers.forecast", side_effect=ProviderError("offline")):
            refresh_trip(self.trip_id, self.now.replace(tzinfo=None) + timedelta(minutes=30))
        self.assertEqual(latest_snapshot(plan).id, snapshot.id)
        self.assertEqual(weather_result(plan)["status"], "stale")

    def test_worker_schedule_lease_and_restart(self):
        plan = self.plan(); now = self.now.replace(tzinfo=None)
        plan.next_refresh_at = now - timedelta(hours=1); plan.lease_until = now + timedelta(minutes=1); plan.lease_token = "other-worker"
        db.session.commit()
        with patch("app.weather.providers.forecast") as fetch:
            self.assertFalse(refresh_trip(self.trip_id, now)); fetch.assert_not_called()
        plan.lease_until = now - timedelta(seconds=1); db.session.commit()
        with patch("app.weather.providers.forecast", return_value=hourly(self.now, 100)):
            self.assertEqual(check_due(now), 1); db.session.remove()
            self.assertEqual(check_due(now + timedelta(minutes=5)), 0)
        self.assertEqual(db.session.get(WeatherPlan, self.trip_id).next_refresh_at, now + timedelta(hours=1))
        trip = db.session.get(Trip, self.trip_id)
        trip.start_date = self.day + timedelta(days=10); trip.end_date = self.day + timedelta(days=12)
        self.assertEqual(refresh_interval(trip, now), timedelta(hours=6))

    def test_revision_isolation_and_completed_trip(self):
        plan = self.plan()
        with patch("app.weather.providers.forecast", return_value=hourly(self.now, 100)):
            refresh_trip(self.trip_id, self.now.replace(tzinfo=None))
        self.client.put(f"/api/trips/{self.trip_id}/weather-plan", json={**self.settings, "outbound_time": "10:00"})
        self.assertIsNone(latest_snapshot(plan))
        self.trip.start_date = self.day - timedelta(days=10); self.trip.end_date = self.day - timedelta(days=9); db.session.commit()
        with patch("app.weather.providers.forecast") as fetch:
            self.assertFalse(refresh_trip(self.trip_id, self.now.replace(tzinfo=None))); fetch.assert_not_called()

    def test_event_read_and_trip_cleanup(self):
        self.plan()
        event = WeatherEvent(trip_id=self.trip_id, revision=1, event_type="weather_change", severity="high", message="Storm", detail={}, dedupe_key="one")
        db.session.add(event); db.session.commit(); base = f"/api/trips/{self.trip_id}/weather/events"
        self.assertTrue(self.client.post(base + f"/{event.id}/read").json["event"]["is_read"])
        self.assertEqual(self.client.post(base + "/999/read").status_code, 404)
        self.assertEqual(len(self.client.get(base).json["events"]), 1)
        self.assertEqual(self.client.delete(f"/api/trips/{self.trip_id}").status_code, 200)
        for model in (WeatherPlan, WeatherSnapshot, WeatherEvent): self.assertEqual(db.session.query(model).count(), 0)

    def test_account_cleanup(self):
        self.plan(); db.session.add(WeatherSnapshot(trip_id=self.trip_id, revision=1, data={})); db.session.commit()
        response = self.client.post("/api/auth/delete-account", json={"password": "test-password-123", "confirmation": "DELETE"})
        self.assertEqual(response.status_code, 200)
        for model in (Trip, WeatherPlan, WeatherSnapshot): self.assertEqual(db.session.query(model).count(), 0)

    def test_refresh_api_cooldown_and_plan_lock(self):
        plan = self.plan()
        base = f"/api/trips/{self.trip_id}"
        with patch("app.weather.providers.forecast", return_value=hourly(self.now, 100)):
            self.assertEqual(self.client.post(base + "/weather/refresh").status_code, 200)
        self.assertEqual(self.client.post(base + "/weather/refresh").status_code, 429)
        plan.lease_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10)
        db.session.commit()
        self.assertEqual(self.client.put(base + "/weather-plan", json=self.settings).status_code, 409)

    def test_out_of_horizon_is_unavailable_not_low_risk(self):
        plan = self.plan()
        self.trip.start_date += timedelta(days=60); self.trip.end_date += timedelta(days=60); db.session.commit()
        with patch("app.weather.providers.forecast") as fetch:
            self.assertTrue(refresh_trip(self.trip_id))
            fetch.assert_not_called()
        result = weather_result(plan)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["forecast"]["flight"]["score"])
        self.assertIsNone(result["forecast"]["retrieved_at"])

    def test_return_monitoring_across_midnight_and_timezones(self):
        self.plan(return_time="23:30")
        settings = {**self.settings, "return_time": "23:30"}
        end = monitoring_end(self.trip, settings)
        departure = datetime.combine(self.trip.end_date, datetime.min.time(), ZoneInfo(DENVER["timezone"])) + timedelta(hours=23, minutes=30)
        self.assertGreaterEqual(end, departure.astimezone(UTC) + timedelta(hours=3))

    def test_shared_flight_window_interface(self):
        result = assess_forecast(DALLAS, self.now, self.now + timedelta(hours=2), hourly(self.now, 4, weather_code=95))
        self.assertEqual(result["status"], "available"); self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["summary"]["severity"], "high")
        with self.assertRaises(ValueError):
            assess_forecast(DALLAS, self.now.replace(tzinfo=None), self.now, [])

    def test_unexpected_refresh_failure_releases_lease(self):
        plan = self.plan()
        with patch("app.weather.providers.forecast", side_effect=RuntimeError("unexpected provider format")), self.assertLogs("app.weather.service", level="ERROR"):
            self.assertFalse(refresh_trip(self.trip_id))
        self.assertIsNone(plan.lease_token); self.assertIsNone(plan.lease_until)
        self.assertIsNotNone(plan.last_error)
        self.assertGreater(plan.next_refresh_at, datetime.now(UTC).replace(tzinfo=None))

    def test_worker_cli(self):
        with patch("app.weather.providers.locations", return_value=[]):
            result = self.app.test_cli_runner().invoke(args=["weather-worker", "--once"])
        self.assertEqual(result.exit_code, 0)


class ModelTests(unittest.TestCase):
    def test_model_missing_invalid_and_preprocessing_parity(self):
        self.assertEqual(predict(CLEAR)["status"], "unavailable")
        manifest = {"schema_version": 1, "target": "weather_disruption", "resolution": "hourly", "format": "logistic-json", "model_version": "test-v1",
            "features": ["rain", "wind_speed_10m"], "units": {"rain": "mm/h", "wind_speed_10m": "km/h"},
            "preprocessing": {"means": [2, 10], "scales": [2, 5]}, "coefficients": [1, 2], "intercept": -1,
            "evaluation": {"held_out": True, "input_kind": "forecast", "brier_score": 0.1, "baseline_brier_score": 0.2}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.json"; path.write_text(json.dumps(manifest))
            result = predict({**CLEAR, "rain": 4}, path)
            self.assertEqual(result["status"], "available"); self.assertAlmostEqual(result["probability"], 0.5)
            self.assertEqual(predict({"rain": None}, path)["status"], "unavailable")
            manifest["units"]["rain"] = "inch/h"; path.write_text(json.dumps(manifest))
            self.assertEqual(predict(CLEAR, path)["status"], "unavailable")
            manifest["units"]["rain"] = "mm/h"
            manifest["evaluation"]["input_kind"] = "historical_observations"; path.write_text(json.dumps(manifest))
            self.assertEqual(predict(CLEAR, path)["status"], "unavailable")
            manifest["evaluation"]["input_kind"] = "forecast"
            manifest["features"] = ["WeatherDelay"]; path.write_text(json.dumps(manifest))
            self.assertEqual(predict(CLEAR, path)["status"], "unavailable")
            path.write_text("not json"); self.assertEqual(predict(CLEAR, path)["status"], "unavailable")


if __name__ == "__main__": unittest.main()
