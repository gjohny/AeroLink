#Tests for the manual live check (AirLabs) and the demo incident script.
#AirLabs is faked here, so these tests never use real requests from the allowance.

#Run from the backend folder with:  python -m unittest tests.test_live_check -v

import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.alerts import incident, live_check, mock_data
from app.alerts.checker import ingest_flight
from app.extensions import db
from app.models import Alert, Trip, TripFlight, User
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    FLIGHT_DELAY_THRESHOLD_MINUTES = 20
    AIRLABS_API_KEY = "test-key"
    AIRLABS_TIMEOUT = 1


TODAY = date(2026, 11, 20)

#What AirLabs' /flight endpoint sends back (only the fields we use)
AIRLABS_FLIGHT = {"flight_iata": "AA100", "flight_icao": "AAL100", "airline_iata": "AA", "airline_name": "American Airlines", "status": "scheduled", "dep_iata": "JFK", "dep_terminal": "8", "dep_gate": "B12", "dep_time": "2026-11-20 18:00", "dep_time_utc": "2026-11-20 23:00", "dep_estimated_utc": "2026-11-20 23:00", "arr_iata": "LHR", "arr_terminal": "3", "arr_gate": "E4", "arr_time": "2026-11-21 06:10", "arr_time_utc": "2026-11-21 06:10", "arr_estimated_utc": "2026-11-21 06:10"}


def airlabs_answer(flight = None, error = None):
    response = MagicMock()
    if error:
        response.json.return_value = {"error": {"code": error}}
    else:
        response.json.return_value = {"response": flight}
    return response


class LiveCheckTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()

        user = User(name = "Owner", email = "owner@example.com")
        user.set_password("password1234")
        db.session.add(user)
        db.session.commit()

        self.trip = Trip(user_id = user.id, destination = "London", start_date = TODAY, end_date = date(2026, 11, 27), travelers = 1, preference_snapshot = {})
        db.session.add(self.trip)
        db.session.commit()

        self.messages = []

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def add_trip_flight(self, number = "AA100", day = TODAY):
        db.session.add(TripFlight(trip_id = self.trip.id, flight_number = number, flight_date = day))
        db.session.commit()

    def run_check(self, *answers):
        with patch("app.alerts.live_check.requests.get", side_effect = list(answers)) as fake_get:
            used = live_check.check_once(TestConfig, today = TODAY, say = self.messages.append)
        return used, fake_get

    def alert_types(self):
        types = []
        for alert in Alert.query.order_by(Alert.id):
            types.append(alert.alert_type)
        return types

    #Converting AirLabs data

    def test_airlabs_flight_becomes_a_checker_record(self):
        record = live_check.airlabs_to_record(AIRLABS_FLIGHT)

        self.assertEqual(record["flight_number"], "AA100")
        self.assertEqual(record["flight_date"], "2026-11-20")
        self.assertEqual(record["scheduled_departure"], "2026-11-20T23:00:00Z")
        self.assertEqual(record["gate"], "B12")
        self.assertEqual(record["arrival_gate"], "E4")
        self.assertEqual(record["airline"], "American Airlines")

        #The record is valid input for the same checker the test data uses
        self.assertEqual(ingest_flight(record, TestConfig), [])

    def test_delay_minutes_are_used_when_there_is_no_estimate(self):
        raw = dict(AIRLABS_FLIGHT, dep_estimated_utc = None, dep_delayed = 50)
        self.assertEqual(live_check.airlabs_to_record(raw)["estimated_departure"], "2026-11-20T23:50:00Z")

    def test_actual_time_wins_once_the_flight_has_left(self):
        raw = dict(AIRLABS_FLIGHT, dep_actual_utc = "2026-11-20 23:40")
        self.assertEqual(live_check.airlabs_to_record(raw)["estimated_departure"], "2026-11-20T23:40:00Z")

    def test_en_route_and_canceled_spellings_are_normalized(self):
        ingest_flight(live_check.airlabs_to_record(AIRLABS_FLIGHT), TestConfig)
        ingest_flight(live_check.airlabs_to_record(dict(AIRLABS_FLIGHT, status = "canceled")), TestConfig)
        self.assertEqual(self.alert_types(), ["cancellation"])

    #Checking trip flights

    def test_live_changes_create_the_same_alerts_as_test_data(self):
        self.add_trip_flight()
        changed = dict(AIRLABS_FLIGHT, dep_gate = "C4", dep_estimated_utc = "2026-11-21 00:00")

        self.run_check(airlabs_answer(AIRLABS_FLIGHT))
        self.run_check(airlabs_answer(changed))

        self.assertEqual(sorted(self.alert_types()), ["delay", "gate_change"])

    def test_only_flights_near_today_are_checked(self):
        self.add_trip_flight(day = date(2026, 12, 15))
        used, fake_get = self.run_check()
        self.assertEqual(used, 0)
        fake_get.assert_not_called()

    def test_each_flight_and_date_is_checked_once(self):
        #The same flight on two trips is still one request
        other_trip = Trip(user_id = self.trip.user_id, destination = "Paris", start_date = TODAY, end_date = TODAY, travelers = 1, preference_snapshot = {})
        db.session.add(other_trip)
        db.session.commit()
        self.add_trip_flight()
        db.session.add(TripFlight(trip_id = other_trip.id, flight_number = "AA100", flight_date = TODAY))
        db.session.commit()

        used, _ = self.run_check(airlabs_answer(AIRLABS_FLIGHT))
        self.assertEqual(used, 1)

    def test_a_different_departure_day_is_skipped(self):
        self.add_trip_flight(day = date(2026, 11, 21))
        used, _ = self.run_check(airlabs_answer(AIRLABS_FLIGHT))

        self.assertEqual(used, 1)
        self.assertEqual(self.alert_types(), [])
        self.assertIn("skipped", self.messages[-1])

    def test_unknown_flight(self):
        self.add_trip_flight()
        self.run_check(airlabs_answer(error = "not_found"))
        self.assertIn("doesn't know", self.messages[-1])

    def test_allowance_reached_stops_the_check(self):
        self.add_trip_flight()
        with self.assertRaises(live_check.LiveDataError):
            self.run_check(airlabs_answer(error = "month_limit_exceeded"))

    def test_missing_api_key(self):
        class NoKey(TestConfig):
            AIRLABS_API_KEY = ""

        with self.assertRaises(live_check.LiveDataError):
            live_check.fetch_airlabs_flight("AA100", NoKey)


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()

        for record in mock_data.demo_records("AA100", "2026-12-01", "on_time"):
            ingest_flight(record, TestConfig)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def incident(self, kind, value = None):
        return incident.make_incident("AA100", "2026-12-01", kind, value, TestConfig)

    def test_gate_change(self):
        created = self.incident("gate")
        self.assertEqual(created[0].alert_type, "gate_change")
        self.assertEqual((created[0].old_value, created[0].new_value), ("B12", "B14"))

    def test_gate_change_to_a_chosen_gate(self):
        self.assertEqual(self.incident("gate", "C7")[0].new_value, "C7")

    def test_delay_moves_departure_and_arrival(self):
        types = []
        for alert in self.incident("delay", "45"):
            types.append(alert.alert_type)
        self.assertEqual(sorted(types), ["arrival_delay", "delay"])

    def test_delays_add_up(self):
        self.incident("delay", "30")
        created = self.incident("delay", "30")
        self.assertIn("60 minutes", created[0].message)

    def test_arrival_gate(self):
        self.assertEqual(self.incident("arrival_gate", "D2")[0].alert_type, "arrival_gate_change")

    def test_cancel(self):
        self.assertEqual(self.incident("cancel")[0].alert_type, "cancellation")

    def test_back_on_time_makes_no_alert(self):
        self.incident("delay")
        self.assertEqual(self.incident("on_time"), [])

    def test_flight_without_data(self):
        with self.assertRaises(ValueError):
            incident.make_incident("UA200", "2026-12-01", "gate", None, TestConfig)

    def test_unknown_incident(self):
        with self.assertRaises(ValueError):
            self.incident("meteor")


if __name__ == "__main__":
    unittest.main()
