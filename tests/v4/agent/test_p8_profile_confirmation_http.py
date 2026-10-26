"""P8 clock metadata follows the real authenticated profile confirmation route."""

import unittest

from mingjing_core.domain.profile_time_basis import validate_profile_time_basis
from tests import test_core_web as web_fixture


class P8ProfileConfirmation(unittest.TestCase):
    setUp = web_fixture.CoreWeb.setUp
    tearDown = web_fixture.CoreWeb.tearDown
    get = web_fixture.CoreWeb.get
    post = web_fixture.CoreWeb.post

    def payload(self, key="profile-p8"):
        self.get("/api/state")
        return {
            "request_id": key,
            "expected_revision": self.repo.get_revision("alpha"),
            "confirmed": True,
            "profile": {
                "gender": "男",
                "birth": {
                    "solar_datetime": "1994-03-12 08:20:31",
                    "precision": "exact",
                    "timezone_offset": 8,
                    "clock_basis": "clock",
                    "location": {"city": "合成地点", "lng": 104.07, "lat": 30.67, "tz": "Asia/Shanghai"},
                },
            },
        }

    def test_explicit_metadata_is_stored_with_actual_source_and_replayed_once(self):
        payload = self.payload()
        result = self.post("/api/subjects/self/profile/confirm", payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.post("/api/subjects/self/profile/confirm", payload).json(), result.json())
        effective = self.get("/api/subjects/self/profile").json()["effective"]
        self.assertEqual(effective["birth.location.tz"], "Asia/Shanghai")
        self.assertEqual(effective["birth.clock_basis"], "clock")
        for field in ("birth.location.tz", "birth.clock_basis"):
            facts = [row for row in self.repo.list("alpha", "fact") if row.get("field") == field]
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0]["consent"], "granted")
            self.assertTrue(facts[0]["source_refs"])
        self.assertEqual(self.client.get("/api/subjects/self/profile").status_code, 401)
        beta = self.client.get("/api/subjects/self/profile", headers={"X-Token": "synthetic-beta"})
        self.assertEqual(beta.status_code, 200)
        self.assertEqual(beta.json()["effective"], {})

    def test_unconfirmed_invalid_or_guessed_metadata_writes_nothing(self):
        for key, value in (("tz", "+08:00"), ("tz", "invalid/timezone"), ("clock_basis", "inferred")):
            payload = self.payload(key + value)
            birth = payload["profile"]["birth"]
            (birth["location"] if key == "tz" else birth)[key] = value
            response = self.post("/api/subjects/self/profile/confirm", payload)
            self.assertIn(response.status_code, (400, 422), response.text)
            self.assertEqual(self.repo.list("alpha", "fact"), [])
        payload = self.payload("not-confirmed")
        payload["confirmed"] = False
        self.assertIn(self.post("/api/subjects/self/profile/confirm", payload).status_code, (400, 422))
        self.assertEqual(self.repo.list("alpha", "fact"), [])

    def test_legacy_payload_remains_legacy_without_inferred_time_metadata(self):
        payload = self.payload("legacy-profile")
        birth = payload["profile"]["birth"]
        del birth["clock_basis"]
        del birth["location"]["tz"]
        result = self.post("/api/subjects/self/profile/confirm", payload)
        self.assertEqual(result.status_code, 200, result.text)
        effective = self.get("/api/subjects/self/profile").json()["effective"]
        self.assertNotIn("birth.location.tz", effective)
        self.assertNotIn("birth.clock_basis", effective)


def test_unknown_clock_basis_is_explicit_not_inferred() -> None:
    assert validate_profile_time_basis({"birth.location.tz": "Asia/Shanghai", "birth.clock_basis": "unknown"}) is None
