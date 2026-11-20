
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret")

from app import create_app
from app.extensions import db
from app.flights import _cache
from app.models import Airport
from config import Config


class FlightTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    AIRLABS_API_KEY = "sample-test-key"
    FLIGHT_CACHE_TTL_SECONDS = 300
    FLIGHT_DELAY_THRESHOLD_MINUTES = 20


def airport(iata, icao, name, lat, lon, id):
    return Airport(id=id, ident=icao, type="large_airport", name=name,
                   municipality="Test City", iso_country="US", iso_region="US-TX",
                   iata_code=iata, icao_code=icao, latitude_deg=lat,
                   longitude_deg=lon, scheduled_service=True)


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status
        self.ok = status < 400

    def json(self):
        return self.body


class AeroLinkFlightApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(FlightTestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)
        db.session.add_all([
            airport("CLL", "KCLL", "Easterwood Field", 30.5886, -96.3638, 1),
            airport("DFW", "KDFW", "DFW Airport", 32.9, -97.04, 2),
            airport("LAX", "KLAX", "Los Angeles Airport", 33.94, -118.41, 3),
        ])
        db.session.commit()
        self.client = self.app.test_client()
        _cache.clear()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        _cache.clear()

    def test_airport_lookup_search_icao_and_invalid_query(self):
        r = self.client.get("/api/airports?q=easterwood")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["airports"][0]["iata_code"], "CLL")
        self.assertEqual(self.client.get("/api/airports/KCLL").json["airport"]["latitude"], 30.5886)
        self.assertEqual(self.client.get("/api/airports?country=US&limit=1").json["count"], 1)
        self.assertEqual(self.client.get("/api/airports/ZZZ").status_code, 404)
        self.assertEqual(self.client.get("/api/airports?country=USA").status_code, 400)

    @patch("app.flights.requests.get")
    def test_single_flight_delay_alert_and_airport_enrichment(self, get):
        get.return_value = FakeResponse({"response": {
            "flight_iata": "AA123", "status": "en-route", "dep_iata": "CLL", "arr_iata": "DFW",
            "dep_time": "2026-11-20 10:00", "dep_estimated": "2026-11-20 10:35",
            "dep_delayed": 35, "arr_delayed": 18,
        }})
        r = self.client.get("/api/flights?flight_iata=aa123")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["source"], "airlabs/flight")
        self.assertEqual(r.json["count"], 1)
        flight = r.json["flights"][0]
        self.assertEqual(flight["departure"]["airport"]["name"], "Easterwood Field")
        self.assertEqual(flight["arrival"]["airport"]["icao_code"], "KDFW")
        self.assertEqual(len(flight["alerts"]), 1)
        self.assertEqual(flight["alerts"][0]["minutes"], 35)
        self.assertEqual(get.call_args.args[0], "https://airlabs.co/api/v9/flight")
        self.assertEqual(get.call_args.kwargs["params"]["flight_iata"], "AA123")
        self.assertEqual(get.call_args.kwargs["params"]["api_key"], "sample-test-key")
        self.assertNotIn("api_key", str(r.json))
        cached = self.client.get("/api/flights?flight_iata=AA123")
        self.assertTrue(cached.json["cached"])
        self.assertEqual(get.call_count, 1)

    @patch("app.flights.requests.get")
    def test_schedule_query_detects_cancelled_and_twenty_minute_delay(self, get):
        get.return_value = FakeResponse({"response": [
            {"flight_iata": "AA11", "dep_iata": "DFW", "arr_iata": "LAX", "status": "cancelled"},
            {"flight_iata": "AA22", "dep_iata": "DFW", "arr_iata": "XXX", "status": "scheduled",
             "dep_delayed": 19, "arr_delayed": 20},
        ]})
        response = self.client.get("/api/flights?dep_iata=dfw&limit=25")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["source"], "airlabs/schedules")
        self.assertEqual(response.json["flights"][0]["alerts"][0]["type"], "cancelled")
        self.assertEqual(response.json["flights"][1]["alerts"][0]["phase"], "arrival")
        self.assertEqual(response.json["flights"][1]["arrival"]["airport"]["name"], None)
        self.assertEqual(get.call_args.kwargs["params"]["limit"], 25)

    @patch("app.flights.requests.get")
    def test_live_mode_and_icao_lookup(self, get):
        get.return_value = FakeResponse({"response": [{
            "flight_icao": "AAL100", "dep_icao": "KCLL", "arr_icao": "KLAX", "status": "en-route",
            "lat": 33.1, "lng": -108.2,
        }]})
        response = self.client.get("/api/flights?flight_icao=AAL100&mode=live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["flights"][0]["departure"]["airport"]["iata_code"], "CLL")
        self.assertEqual(response.json["flights"][0]["position"]["longitude"], -108.2)
        self.assertEqual(get.call_args.args[0], "https://airlabs.co/api/v9/flights")

    @patch("app.flights.requests.get")
    def test_invalid_requests_do_not_spend_quota(self, get):
        for path in ("/api/flights", "/api/flights?flight_iata=bad!",
                     "/api/flights?dep_iata=AB", "/api/flights?dep_iata=DFW&limit=51",
                     "/api/flights?dep_iata=DFW&api_key=leaked"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 400)
        get.assert_not_called()

    @patch("app.flights.requests.get")
    def test_provider_rate_limit_error_and_missing_key(self, get):
        get.return_value = FakeResponse({"error": {"code": "month_limit_exceeded", "message": "quota"}})
        response = self.client.get("/api/flights?flight_iata=AA123")
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("sample-test-key", str(response.json))
        self.app.config["AIRLABS_API_KEY"] = ""
        response = self.client.get("/api/flights?flight_iata=AA123")
        self.assertEqual(response.status_code, 503)

    @patch("app.flights.requests.get")
    def test_empty_result_and_legacy_delay_fallback(self, get):
        get.return_value = FakeResponse({"response": []})
        response = self.client.get("/api/flights?flight_iata=AA999")
        self.assertEqual(response.json["flights"], [])
        _cache.clear()
        get.return_value = FakeResponse({"response": {"flight_iata": "AA999", "delayed": 24}})
        response = self.client.get("/api/flights?flight_iata=AA999")
        self.assertEqual(response.json["flights"][0]["alerts"][0]["minutes"], 24)


if __name__ == "__main__":
    unittest.main()
