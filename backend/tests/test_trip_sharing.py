import os
import unittest
from unittest.mock import patch

# config.py reads SECRET_KEY when it is imported, so set one for the tests
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


TRIP = {"destination": "Rome, Italy", "start_date": "2026-12-01", "end_date": "2026-12-08", "travelers": 2, "use_saved_preferences": True}


class TripSharingTests(unittest.TestCase):
    def setUp(self):
        # Don't contact Unsplash during tests
        photo_patch = patch("app.trips.find_destination_photo", return_value = None)
        photo_patch.start()
        self.addCleanup(photo_patch.stop)

        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)

        # One browser (test client) per person, so each keeps its own login
        self.owner = self.make_user("Owner", "owner@example.com")
        self.friend = self.make_user("Friend", "friend@example.com")
        self.stranger = self.make_user("Stranger", "stranger@example.com")

        self.trip_id = self.owner.post("/api/trips", json = TRIP).get_json()["trip"]["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    def make_user(self, name, email):
        client = self.app.test_client()
        response = client.post("/api/auth/register", json = {"name": name, "email": email, "password": "password1234"})
        self.assertEqual(response.status_code, 201)

        return client

    def share(self):
        response = self.owner.post(f"/api/trips/{self.trip_id}/share")
        self.assertEqual(response.status_code, 200)

        return response.get_json()["code"]

    def join(self, client, code):
        return client.post("/api/trips/join", json = {"code": code})

    def test_owner_gets_a_readable_code(self):
        code = self.share()
        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")

    def test_sharing_again_returns_the_same_code(self):
        self.assertEqual(self.share(), self.share())

    def test_friend_joins_and_sees_the_same_trip(self):
        code = self.share()
        response = self.join(self.friend, code)
        self.assertEqual(response.status_code, 201)

        trip = response.get_json()["trip"]
        self.assertEqual(trip["id"], self.trip_id)
        self.assertFalse(trip["is_owner"])
        self.assertEqual(trip["owner_name"], "Owner")

        listed = self.friend.get("/api/trips").get_json()["trips"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], self.trip_id)
        self.assertEqual(self.friend.get(f"/api/trips/{self.trip_id}").status_code, 200)

    def test_owner_sees_who_the_trip_is_shared_with(self):
        self.join(self.friend, self.share())
        trip = self.owner.get(f"/api/trips/{self.trip_id}").get_json()["trip"]
        self.assertTrue(trip["is_owner"])
        self.assertEqual(trip["shared_with"], ["Friend"])

    def test_code_is_accepted_in_lowercase_without_the_dash(self):
        code = self.share().replace("-", "").lower()
        self.assertEqual(self.join(self.friend, code).status_code, 201)

    def test_wrong_code_and_bad_input(self):
        self.share()
        self.assertEqual(self.join(self.friend, "ZZZZ-ZZZZ").status_code, 404)
        self.assertEqual(self.join(self.friend, "ABC").status_code, 400)
        self.assertEqual(self.friend.post("/api/trips/join", json = {}).status_code, 400)

    def test_cannot_join_own_trip_or_join_twice(self):
        code = self.share()
        self.assertEqual(self.join(self.owner, code).status_code, 409)
        self.join(self.friend, code)
        self.assertEqual(self.join(self.friend, code).status_code, 409)

    def test_stranger_cannot_see_the_trip(self):
        self.share()
        self.assertEqual(self.stranger.get(f"/api/trips/{self.trip_id}").status_code, 404)
        self.assertEqual(self.stranger.get("/api/trips").get_json()["trips"], [])

    def test_member_cannot_reshare(self):
        self.join(self.friend, self.share())
        self.assertEqual(self.friend.post(f"/api/trips/{self.trip_id}/share").status_code, 403)

    def test_member_cannot_delete_but_can_leave(self):
        self.join(self.friend, self.share())
        self.assertEqual(self.friend.delete(f"/api/trips/{self.trip_id}").status_code, 403)

        self.assertEqual(self.friend.post(f"/api/trips/{self.trip_id}/leave").status_code, 200)
        self.assertEqual(self.friend.get("/api/trips").get_json()["trips"], [])

        # The owner still has the trip
        self.assertEqual(len(self.owner.get("/api/trips").get_json()["trips"]), 1)

    def test_owner_cannot_leave(self):
        self.assertEqual(self.owner.post(f"/api/trips/{self.trip_id}/leave").status_code, 400)

    def test_owner_delete_removes_it_for_everyone(self):
        code = self.share()
        self.join(self.friend, code)
        self.assertEqual(self.owner.delete(f"/api/trips/{self.trip_id}").status_code, 200)

        self.assertEqual(self.friend.get("/api/trips").get_json()["trips"], [])
        
        # The old code no longer works
        self.assertEqual(self.join(self.stranger, code).status_code, 404)

    def test_must_be_logged_in(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.post(f"/api/trips/{self.trip_id}/share").status_code, 401)
        self.assertEqual(anonymous.post("/api/trips/join", json = {"code": "ABCD-EFGH"}).status_code, 401)
        self.assertEqual(anonymous.post(f"/api/trips/{self.trip_id}/leave").status_code, 401)
        self.assertEqual(anonymous.delete(f"/api/trips/{self.trip_id}/share").status_code, 401)
        self.assertEqual(anonymous.delete(f"/api/trips/{self.trip_id}/members/1").status_code, 401)

    def member_id(self, name):
        members = self.owner.get(f"/api/trips/{self.trip_id}").get_json()["trip"]["members"]
        for member in members:
            if member["name"] == name:
                return member["id"]

        return None

    def test_owner_sees_member_ids_but_members_do_not(self):
        self.join(self.friend, self.share())
        owner_view = self.owner.get(f"/api/trips/{self.trip_id}").get_json()["trip"]
        friend_view = self.friend.get(f"/api/trips/{self.trip_id}").get_json()["trip"]

        self.assertEqual(owner_view["members"][0]["name"], "Friend")
        self.assertNotIn("members", friend_view)

    def test_owner_removes_one_person_and_others_stay(self):
        code = self.share()
        self.join(self.friend, code)
        self.join(self.stranger, code)

        response = self.owner.delete(f"/api/trips/{self.trip_id}/members/{self.member_id('Friend')}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["trip"]["shared_with"], ["Stranger"])

        self.assertEqual(self.friend.get("/api/trips").get_json()["trips"], [])
        self.assertEqual(len(self.stranger.get("/api/trips").get_json()["trips"]), 1)

    def test_removed_person_cannot_rejoin_with_old_code(self):
        code = self.share()
        self.join(self.friend, code)
        self.owner.delete(f"/api/trips/{self.trip_id}/members/{self.member_id('Friend')}")

        self.assertEqual(self.join(self.friend, code).status_code, 404)

        # Sharing again gives a new code that works
        new_code = self.share()
        self.assertNotEqual(new_code, code)
        self.assertEqual(self.join(self.friend, new_code).status_code, 201)

    def test_stop_sharing_removes_everyone_but_keeps_the_trip(self):
        code = self.share()
        self.join(self.friend, code)
        self.join(self.stranger, code)

        response = self.owner.delete(f"/api/trips/{self.trip_id}/share")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["trip"]["shared_with"], [])

        self.assertEqual(self.friend.get("/api/trips").get_json()["trips"], [])
        self.assertEqual(self.stranger.get("/api/trips").get_json()["trips"], [])
        self.assertEqual(len(self.owner.get("/api/trips").get_json()["trips"]), 1)
        self.assertEqual(self.join(self.friend, code).status_code, 404)

    def test_members_cannot_remove_people_or_stop_sharing(self):
        code = self.share()
        self.join(self.friend, code)
        self.join(self.stranger, code)
        stranger_id = self.member_id("Stranger")

        self.assertEqual(self.friend.delete(f"/api/trips/{self.trip_id}/members/{stranger_id}").status_code, 403)
        self.assertEqual(self.friend.delete(f"/api/trips/{self.trip_id}/share").status_code, 403)

    def test_removing_someone_not_on_the_trip(self):
        self.assertEqual(self.owner.delete(f"/api/trips/{self.trip_id}/members/9999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
