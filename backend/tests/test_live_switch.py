#Tests for the LIVE_FLIGHT_DATA switch: with it off (the default), flight searches and Look up use flights
#saved in the database and never call AirLabs. With it on, they use AirLabs.

#Run from the backend folder with:  python -m unittest tests.test_live_switch -v

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.alerts import mock_data
from app.alerts.checker import ingest_flight
from app.extensions import db
from app.flights import _cache
from config import Config


class LiveOff(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    AIRLABS_API_KEY = "test-key"
    LIVE_FLIGHT_DATA = False


class LiveOn(LiveOff):
    LIVE_FLIGHT_DATA = True


AIRLABS_FLIGHT = {"flight_iata": "AA100", "airline_name": "American Airlines", "status": "scheduled", "dep_iata": "JFK", "dep_time": "2026-12-01 18:00", "dep_time_utc": "2026-12-01 23:00", "arr_iata": "LHR", "arr_time_utc": "2026-12-02 06:10"}


def airlabs_answer(flight):
    response = MagicMock()
    response.status_code = 200
    response.ok = True
    response.json.return_value = {"response": flight}
    return response


class SwitchTestCase(unittest.TestCase):
    config = LiveOff

    def setUp(self):
        _cache.clear()
        self.app = create_app(self.config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()
        self.client.post("/api/auth/register", json = {"name": "Tester", "email": "tester@example.com", "password": "password1234"})

        #Test data for one flight, like running: python -m app.alerts.mock_data AA100 2026-12-01 delayed
        for record in mock_data.demo_records("AA100", "2026-12-01", "delayed"):
            ingest_flight(record, self.config)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()


class LiveOffTests(SwitchTestCase):
    def test_default_setting_is_off(self):
        self.assertFalse(Config.LIVE_FLIGHT_DATA)

    def test_flight_search_uses_saved_flights(self):
        with patch("app.flights.requests.get") as fake_get:
            body = self.client.get("/api/flights?flight_iata=AA100").get_json()
        fake_get.assert_not_called()

        self.assertFalse(body["live"])
        self.assertEqual(body["source"], "database")
        self.assertEqual(body["count"], 1)

        flight = body["flights"][0]
        self.assertEqual(flight["status"], "delayed")
        self.assertEqual(flight["departure"]["airport"]["iata_code"], "ORD")
        self.assertEqual(flight["departure"]["scheduled"], "2026-12-01 15:10 UTC")
        self.assertEqual(flight["departure"]["delay_minutes"], 55)
        self.assertEqual(flight["alerts"], [])

    def test_search_by_airport(self):
        self.assertEqual(self.client.get("/api/flights?dep_iata=ORD").get_json()["count"], 1)
        self.assertEqual(self.client.get("/api/flights?dep_iata=LAX").get_json()["count"], 0)

    def test_search_still_validates_input(self):
        self.assertEqual(self.client.get("/api/flights").status_code, 400)

    def test_look_up_finds_test_data(self):
        with patch("app.flights.requests.get") as fake_get:
            body = self.client.get("/api/flights/lookup?flight_number=aa 100&flight_date=2026-12-01").get_json()
        fake_get.assert_not_called()

        self.assertTrue(body["found"])
        self.assertEqual(body["source"], "database")
        self.assertEqual((body["departure_airport"], body["arrival_airport"]), ("ORD", "FCO"))

    def test_look_up_on_another_date_still_fills_airports(self):
        body = self.client.get("/api/flights/lookup?flight_number=AA100&flight_date=2026-12-09").get_json()
        self.assertTrue(body["found"])
        self.assertEqual(body["flight_date"], "2026-12-01")
        self.assertIn("not on the date you chose", body["message"])

    def test_look_up_missing_flight_says_how_to_add_it(self):
        body = self.client.get("/api/flights/lookup?flight_number=UA200&flight_date=2026-12-01").get_json()
        self.assertFalse(body["found"])
        self.assertIn("python -m app.alerts.mock_data UA200 2026-12-01 on_time", body["message"])

    def test_look_up_needs_login_and_a_number(self):
        self.assertEqual(self.app.test_client().get("/api/flights/lookup?flight_number=AA100").status_code, 401)
        self.assertEqual(self.client.get("/api/flights/lookup").status_code, 400)
        self.assertEqual(self.client.get("/api/flights/lookup?flight_number=AA100&flight_date=soon").status_code, 400)


class LiveOnTests(SwitchTestCase):
    config = LiveOn

    def test_flight_search_uses_airlabs(self):
        with patch("app.flights.requests.get", return_value = airlabs_answer(AIRLABS_FLIGHT)) as fake_get:
            body = self.client.get("/api/flights?flight_iata=AA100").get_json()
        fake_get.assert_called_once()
        self.assertTrue(body["live"])
        self.assertEqual(body["flights"][0]["departure"]["airport"]["iata_code"], "JFK")

    def test_look_up_uses_airlabs(self):
        with patch("app.flights.requests.get", return_value = airlabs_answer(AIRLABS_FLIGHT)) as fake_get:
            body = self.client.get("/api/flights/lookup?flight_number=AA100&flight_date=2026-12-01").get_json()
        fake_get.assert_called_once()

        self.assertEqual(body["source"], "live")
        self.assertEqual((body["departure_airport"], body["arrival_airport"]), ("JFK", "LHR"))
        self.assertEqual(body["airline"], "American Airlines")

    def test_look_up_reports_when_airlabs_has_a_different_day(self):
        with patch("app.flights.requests.get", return_value = airlabs_answer(AIRLABS_FLIGHT)):
            body = self.client.get("/api/flights/lookup?flight_number=AA100&flight_date=2026-12-20").get_json()
        self.assertIn("next departure", body["message"])

    def test_look_up_without_a_key(self):
        self.app.config["AIRLABS_API_KEY"] = ""
        self.assertEqual(self.client.get("/api/flights/lookup?flight_number=AA100").status_code, 503)


if __name__ == "__main__":
    unittest.main()
