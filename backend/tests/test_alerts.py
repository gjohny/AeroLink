#Tests for the flag rules, the checker, and the alert endpoints

#Run from the backend folder with:  python -m unittest tests.test_alerts -v

import unittest

from app import create_app
from app.alerts import checker, mock_data
from app.extensions import db
from app.models import Alert
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DELAY_THRESHOLD_MINUTES = 20


class AlertTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def load(self, records):
        for record in records:
            checker.ingest_flight(record, TestConfig)

    def types(self):
        alert_types = []
        for a in Alert.query.order_by(Alert.id):
            alert_types.append(a.alert_type)
            
        return alert_types


class RuleAndCheckerTests(AlertTestCase):
    def test_normal_flight_makes_no_alerts(self):
        self.load(mock_data.NORMAL)
        self.assertEqual(self.types(), [])

    def test_delay_over_threshold_makes_one_alert(self):
        self.load(mock_data.DELAYED)
        self.assertEqual(self.types(), ["delay"])

    def test_delay_just_under_threshold_makes_no_alert(self):
        self.load([dict(mock_data.DELAYED[1], estimated_departure = "2026-11-02T15:29:00Z")])
        self.assertEqual(self.types(), [])

    def test_gate_change_makes_alert(self):
        self.load(mock_data.GATE_CHANGED)
        self.assertEqual(self.types(), ["gate_change"])

    def test_cancellation_makes_one_alert_and_no_delay_alert(self):
        self.load(mock_data.CANCELLED)
        self.assertEqual(self.types(), ["cancellation"])

    def test_same_update_twice_does_not_repeat_alert(self):
        self.load(mock_data.DELAYED + [mock_data.DELAYED[-1]])
        self.assertEqual(self.types(), ["delay"])

    def test_delay_getting_worse_makes_a_new_alert(self):
        self.load(mock_data.DELAYED)
        self.load([dict(mock_data.DELAYED[-1], estimated_departure = "2026-11-02T16:10:00Z")])
        self.assertEqual(self.types(), ["delay", "delay"])

    def test_times_with_offsets_are_converted_to_utc(self):
        #10:10 at UTC-5 is 15:10 UTC, so this flight is on time
        record = dict(mock_data.DELAYED[0], scheduled_departure = "2026-11-02T10:10:00-05:00", estimated_departure="2026-11-02T15:10:00Z")

        self.load([record])
        self.assertEqual(self.types(), [])

    def test_missing_field_is_rejected(self):
        with self.assertRaises(ValueError):
            checker.ingest_flight({"flight_number": "XX1"}, TestConfig)

    def test_bad_time_is_rejected(self):
        with self.assertRaises(ValueError):
            checker.ingest_flight(dict(mock_data.NORMAL[0], estimated_departure="tomorrow-ish"), TestConfig)


class ApiTests(AlertTestCase):
    def test_post_flights_then_list_and_mark_read(self):
        for record in mock_data.DELAYED:
            res = self.client.post("/api/flights", json=record)
            self.assertEqual(res.status_code, 201)

        alerts = self.client.get("/api/alerts").get_json()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "delay")
        self.assertFalse(alerts[0]["is_read"])
        self.assertTrue(alerts[0]["created_at"].endswith("Z"))

        res = self.client.post(f"/api/alerts/{alerts[0]['id']}/read")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/api/alerts?unread=1").get_json(), [])

    def test_read_all(self):
        for scenario in (mock_data.DELAYED, mock_data.GATE_CHANGED, mock_data.CANCELLED):
            for record in scenario:
                self.client.post("/api/flights", json = record)

        self.assertEqual(len(self.client.get("/api/alerts?unread=1").get_json()), 3)
        res = self.client.post("/api/alerts/read-all")
        self.assertEqual(res.get_json(), {"updated": 3})
        self.assertEqual(self.client.get("/api/alerts?unread=1").get_json(), [])

    def test_bad_flight_record_returns_400(self):
        res = self.client.post("/api/flights", json={"flight_number": "XX1"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("missing", res.get_json()["error"])

    def test_empty_body_returns_400(self):
        self.assertEqual(self.client.post("/api/flights").status_code, 400)

    def test_mark_read_unknown_alert_returns_404(self):
        self.assertEqual(self.client.post("/api/alerts/999/read").status_code, 404)

    def test_existing_task_endpoints_still_work(self):
        res = self.client.post("/api/tasks", json = {"title": "still here"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.client.get("/api/health").get_json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
