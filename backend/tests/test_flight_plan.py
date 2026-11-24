#Tests for the Flight Plan page routes and for alerts being tied to a user's trips

#Run from the backend folder with:  python -m unittest tests.test_flight_plan -v

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.alerts import checker, mock_data
from app.extensions import db
from app.models import Airport
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    FLIGHT_DELAY_THRESHOLD_MINUTES = 20


TRIP = {"destination": "Rome, Italy", "start_date": "2026-12-01", "end_date": "2026-12-08", "travelers": 2, "use_saved_preferences": True}


class FlightPlanTests(unittest.TestCase):
    def setUp(self):
        #Don't contact Unsplash during tests
        photo_patch = patch("app.trips.find_destination_photo", return_value = None)
        photo_patch.start()
        self.addCleanup(photo_patch.stop)

        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()

        self.owner = self.make_user("Owner", "owner@example.com")
        self.friend = self.make_user("Friend", "friend@example.com")
        self.stranger = self.make_user("Stranger", "stranger@example.com")

        self.trip_id = self.owner.post("/api/trips", json = TRIP).get_json()["trip"]["id"]

        #Friend joins the trip with a share code
        code = self.owner.post(f"/api/trips/{self.trip_id}/share").get_json()["code"]
        self.friend.post("/api/trips/join", json = {"code": code})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def make_user(self, name, email):
        client = self.app.test_client()
        client.post("/api/auth/register", json = {"name": name, "email": email, "password": "password1234"})
        return client

    def add_flight(self, client = None, **fields):
        body = {"flight_number": "AA100", "flight_date": "2026-12-01"}
        body.update(fields)
        return (client or self.owner).post(f"/api/trips/{self.trip_id}/flights", json = body)

    def flights(self, client = None):
        return (client or self.owner).get(f"/api/trips/{self.trip_id}/flights").get_json()["flights"]

    def play(self, name, flight_number = "AA100", flight_date = "2026-12-01"):
        for record in mock_data.demo_records(flight_number, flight_date, name):
            checker.ingest_flight(record, TestConfig)

    #Adding, swapping, removing

    def test_owner_adds_a_flight_and_it_waits_for_live_data(self):
        res = self.add_flight(flight_number = "aa 100", departure_airport = "ord", arrival_airport = "fco")
        self.assertEqual(res.status_code, 201)

        flight = res.get_json()["flight"]
        self.assertEqual(flight["flight_number"], "AA100")
        self.assertFalse(flight["has_live_data"])
        self.assertEqual(flight["departure"]["code"], "ORD")
        self.assertEqual(flight["arrival"]["code"], "FCO")

    def test_flight_number_and_date_are_checked(self):
        self.assertEqual(self.add_flight(flight_number = "hello").status_code, 400)
        self.assertEqual(self.add_flight(flight_date = "").status_code, 400)
        self.assertEqual(self.add_flight(flight_date = "12/01/2026").status_code, 400)
        self.assertEqual(self.add_flight(departure_airport = "CHICAGO").status_code, 400)
        self.assertEqual(self.add_flight(departure_airport = "ORD", arrival_airport = "ORD").status_code, 400)

    def test_airport_codes_are_checked_when_the_airport_table_is_loaded(self):
        db.session.add(Airport(id = 1, ident = "KORD", type = "large_airport", name = "Chicago O'Hare International Airport", municipality = "Chicago", iso_country = "US", iata_code = "ORD", latitude_deg = 41.9, longitude_deg = -87.9, scheduled_service = True))
        db.session.commit()

        self.assertEqual(self.add_flight(departure_airport = "ZZZ").status_code, 400)

        flight = self.add_flight(departure_airport = "ORD").get_json()["flight"]
        self.assertEqual(flight["departure"]["name"], "Chicago O'Hare International Airport")
        self.assertEqual(flight["departure"]["city"], "Chicago")

    def test_same_flight_twice_is_rejected(self):
        self.add_flight()
        self.assertEqual(self.add_flight(flight_number = "AA 100").status_code, 409)

    def test_owner_swaps_a_flight(self):
        flight_id = self.add_flight().get_json()["flight"]["id"]
        res = self.owner.put(f"/api/trips/{self.trip_id}/flights/{flight_id}", json = {"flight_number": "UA200", "flight_date": "2026-12-02"})
        self.assertEqual(res.status_code, 200)

        flights = self.flights()
        self.assertEqual(len(flights), 1)
        self.assertEqual((flights[0]["flight_number"], flights[0]["flight_date"]), ("UA200", "2026-12-02"))

    def test_owner_removes_a_flight(self):
        flight_id = self.add_flight().get_json()["flight"]["id"]
        self.assertEqual(self.owner.delete(f"/api/trips/{self.trip_id}/flights/{flight_id}").status_code, 200)
        self.assertEqual(self.flights(), [])

    def test_members_can_see_but_not_change_flights(self):
        flight_id = self.add_flight().get_json()["flight"]["id"]

        res = self.friend.get(f"/api/trips/{self.trip_id}/flights").get_json()
        self.assertFalse(res["trip"]["is_owner"])
        self.assertEqual(len(res["flights"]), 1)

        self.assertEqual(self.add_flight(client = self.friend, flight_number = "UA200").status_code, 403)
        self.assertEqual(self.friend.put(f"/api/trips/{self.trip_id}/flights/{flight_id}", json = {"flight_number": "UA200", "flight_date": "2026-12-02"}).status_code, 403)
        self.assertEqual(self.friend.delete(f"/api/trips/{self.trip_id}/flights/{flight_id}").status_code, 403)

    def test_strangers_and_logged_out_users_cannot_see_flights(self):
        self.add_flight()
        self.assertEqual(self.stranger.get(f"/api/trips/{self.trip_id}/flights").status_code, 404)
        self.assertEqual(self.app.test_client().get(f"/api/trips/{self.trip_id}/flights").status_code, 401)

    def test_deleting_the_trip_removes_its_flights(self):
        self.add_flight()
        self.play("delayed")
        self.owner.delete(f"/api/trips/{self.trip_id}")
        self.assertEqual(self.owner.get("/api/alerts").get_json(), [])

    #Live data, changes, and alerts on the card

    def test_live_data_fills_in_the_card(self):
        self.add_flight()
        self.play("on_time")

        flight = self.flights()[0]
        self.assertTrue(flight["has_live_data"])
        self.assertEqual(flight["status"], "scheduled")
        self.assertEqual(flight["airline"], "Demo Airlines")
        self.assertEqual(flight["departure"]["gate"], "B12")
        self.assertEqual(flight["arrival"]["gate"], "E4")
        self.assertEqual(flight["departure"]["scheduled"], "2026-12-01T15:10:00Z")
        self.assertEqual(flight["changes"], {"departure_time": None, "arrival_time": None, "departure_gate": None, "arrival_gate": None})

    def test_delay_shows_old_and_new_times(self):
        self.add_flight()
        self.play("delayed")

        changes = self.flights()[0]["changes"]
        self.assertEqual(changes["departure_time"], {"type": "delay", "old": "2026-12-01T15:10:00Z", "new": "2026-12-01T16:05:00Z"})
        self.assertEqual(changes["arrival_time"]["type"], "arrival_delay")

    def test_gate_change_shows_old_and_new_gate(self):
        self.add_flight()
        self.play("gate_change")
        self.assertEqual(self.flights()[0]["changes"]["departure_gate"], {"type": "gate_change", "old": "B12", "new": "C4"})

    def test_arrival_changes_make_alerts(self):
        self.add_flight()
        self.play("arrival_changes")

        flight = self.flights()[0]
        types = []
        for alert in flight["alerts"]:
            types.append(alert["alert_type"])

        self.assertEqual(sorted(types), ["arrival_delay", "arrival_gate_change"])
        self.assertEqual(flight["changes"]["arrival_gate"], {"type": "arrival_gate_change", "old": "E4", "new": "D7"})

    def test_cancelled_flight(self):
        self.add_flight()
        self.play("cancelled")

        flight = self.flights()[0]
        self.assertEqual(flight["status"], "cancelled")
        self.assertEqual(flight["alerts"][0]["alert_type"], "cancellation")

    def test_same_number_on_another_day_is_a_different_flight(self):
        self.add_flight()
        self.play("delayed", flight_date = "2026-12-05")

        flight = self.flights()[0]
        self.assertFalse(flight["has_live_data"])
        self.assertEqual(flight["alerts"], [])

    #The bell: alerts belong to the user's trips, read state is per person

    def test_bell_only_shows_alerts_for_my_trips(self):
        self.add_flight()
        self.play("delayed")
        self.play("cancelled", flight_number = "ZZ999")

        owner_types = []
        for alert in self.owner.get("/api/alerts").get_json():
            owner_types.append(alert["alert_type"])

        self.assertEqual(sorted(owner_types), ["arrival_delay", "delay"])
        self.assertEqual(len(self.friend.get("/api/alerts").get_json()), 2)
        self.assertEqual(self.stranger.get("/api/alerts").get_json(), [])

    def test_read_state_is_per_person(self):
        self.add_flight()
        self.play("gate_change")
        alert_id = self.owner.get("/api/alerts").get_json()[0]["id"]

        self.owner.post(f"/api/alerts/{alert_id}/read")
        self.assertTrue(self.owner.get("/api/alerts").get_json()[0]["is_read"])
        self.assertFalse(self.friend.get("/api/alerts").get_json()[0]["is_read"])

    def test_cannot_mark_someone_elses_alert(self):
        self.add_flight()
        self.play("gate_change")
        alert_id = self.owner.get("/api/alerts").get_json()[0]["id"]
        self.assertEqual(self.stranger.post(f"/api/alerts/{alert_id}/read").status_code, 404)

    def test_removed_flight_alerts_leave_the_bell(self):
        flight_id = self.add_flight().get_json()["flight"]["id"]
        self.play("delayed")
        self.owner.delete(f"/api/trips/{self.trip_id}/flights/{flight_id}")
        self.assertEqual(self.owner.get("/api/alerts").get_json(), [])


if __name__ == "__main__":
    unittest.main()
