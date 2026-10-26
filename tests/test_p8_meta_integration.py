"""Charts-native P8 wiring checks, using only explicitly synthetic birth inputs."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter  # noqa: E402
from mingjing_core.adapters.charts.profile_draft import profile_proposal  # noqa: E402

OWNER = "synthetic-meta-owner"
SUBJECT = "synthetic-meta-subject"
REVISION = 7
PERIOD = {
    "start_at": "2026-03-19T00:00:00Z",
    "end_at": "2026-03-22T00:00:00Z",
    "moving_bodies": ["太阳"],
}


def archive() -> dict[str, Any]:
    return {
        "owner_user_id": OWNER,
        "subject_id": SUBJECT,
        "user": {
            "gender": "男",
            "birth": {
                "solar_datetime": "2000-03-20 12:00",
                "time_precision": "exact",
                "calendar": "solar",
                "timezone_offset": 8,
                "location": {"lng": 120, "lat": 30},
                "input_status": {"source": "explicitly_synthetic_integration_fixture"},
            },
        },
    }


def pointer(document: Any, path: str) -> Any:
    value = document
    for encoded in path.split("/")[1:]:
        key = encoded.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


class MetaIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = P8ChartAdapter(
            OWNER, python=sys.executable, transit_period=PERIOD
        )
        cls.calculation = cls.adapter.calculate(
            archive(), "2026-03-20", ["bazi", "ziwei", "astro"], REVISION, SUBJECT
        )
        if cls.calculation["errors"]:
            raise AssertionError("synthetic three-system P8 calculation failed")
        cls.artifacts = {
            item["system"]: item for item in cls.calculation["artifacts"].values()
        }
        uncertain = archive()
        uncertain["user"]["birth"].update(
            time_precision="approximate", time_uncertainty_minutes=61
        )
        cls.multiple = cls.adapter.calculate(
            uncertain, "2026-03-20", ["bazi"], REVISION, SUBJECT
        )
        if cls.multiple["errors"]:
            raise AssertionError("synthetic multi-branch P8 calculation failed")

    def test_all_three_systems_publish_resolvable_feature_pointers(self) -> None:
        self.assertEqual(set(self.artifacts), {"bazi", "ziwei", "astro"})
        features = self.calculation["features"].values()
        self.assertTrue(features)
        for feature in features:
            artifact = self.calculation["artifacts"][feature["artifact_id"]]
            self.assertEqual(pointer(artifact, feature["path"]), feature["value"])
            self.assertEqual(feature["owner_user_id"], OWNER)
            self.assertEqual(feature["revision"], REVISION)
        paths = {item["path"] for item in features}
        self.assertTrue(
            {
                "/data/p8/time_interactions",
                "/data/p8_time_interactions",
                "/data/p8_transit_windows",
            }
            <= paths
        )

    def test_ziwei_yearly_links_match_actual_engine_mutagen_and_palaces(self) -> None:
        data = self.artifacts["ziwei"]["data"]
        links = data["p8_time_interactions"]
        actual = data["horoscope"]["yearly"]["mutagen_links"]
        self.assertTrue(links["complete"])
        self.assertEqual(len(links["links"]), 4)
        for linked, reference in zip(links["links"], actual, strict=True):
            self.assertEqual(linked["status"], "resolved")
            self.assertEqual(linked["star"], reference["star"])
            location = linked["locations"][0]
            self.assertEqual(location["palace_index"], reference["palace_index"])
            self.assertEqual(location["yearly_palace"], reference["scope_palace"])
            self.assertEqual(
                pointer(self.artifacts["ziwei"], location["star_pointer"])["name"],
                location["natal_palace"],
            )

    def test_astro_constructor_injects_real_sun_transit_window(self) -> None:
        artifact = self.artifacts["astro"]
        data = artifact["data"]["p8_transit_windows"]
        self.assertEqual(
            data["requested_interval"],
            {
                "start": PERIOD["start_at"],
                "end": PERIOD["end_at"],
            },
        )
        self.assertTrue(data["windows"])
        conjunctions = [
            row
            for row in data["windows"]
            if row["from"] == row["to"] == "太阳" and row["aspect"] == "合相"
        ]
        self.assertTrue(conjunctions)
        self.assertTrue(any(row["exact_at"] for row in conjunctions))
        for row in data["windows"]:
            self.assertEqual(row["from"], "太阳")
            self.assertLess(row["window_start"], row["window_end"])
        profile = self.calculation["profiles"][artifact["profile_id"]]
        self.assertEqual(profile["actual_method"]["p8_transit_interval"], PERIOD)

    def test_new_calculation_source_fingerprints_cover_actual_interaction_code(
        self,
    ) -> None:
        required = {
            "bazi": "interactions_bazi.py",
            "ziwei": "interactions_ziwei.py",
            "astro": "interactions_transits.py",
        }
        for system, filename in required.items():
            profile = self.calculation["profiles"][self.artifacts[system]["profile_id"]]
            hashes = profile["versions"]["p8"]["source_sha256"]
            path = "mingjing_core/adapters/charts/" + filename
            expected = hashlib.sha256(
                (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            self.assertEqual(hashes[path], expected)

    def test_profile_proposal_same_payload_is_idempotent_and_read_only(self) -> None:
        before = deepcopy(self.calculation)
        first = profile_proposal(self.calculation, OWNER, SUBJECT, REVISION)
        second = profile_proposal(self.calculation, OWNER, SUBJECT, REVISION)
        self.assertEqual(first, second)
        self.assertEqual(first["writes"], 0)
        self.assertEqual(self.calculation, before)

    def test_profile_change_requires_nonblank_reason_and_versions_change(self) -> None:
        first = profile_proposal(self.calculation, OWNER, SUBJECT, REVISION)
        for reason in (None, "", " "):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                profile_proposal(
                    self.calculation,
                    OWNER,
                    SUBJECT,
                    REVISION,
                    previous_version=first["version_id"],
                    change_reason=reason,
                )
        revised = profile_proposal(
            self.calculation,
            OWNER,
            SUBJECT,
            REVISION,
            previous_version=first["version_id"],
            change_reason="合成口径复核",
        )
        self.assertNotEqual(first["version_id"], revised["version_id"])

    def test_profile_cross_owner_subject_or_revision_is_rejected(self) -> None:
        for owner, subject, revision in (
            ("other-owner", SUBJECT, REVISION),
            (OWNER, "other-subject", REVISION),
            (OWNER, SUBJECT, REVISION + 1),
        ):
            with (
                self.subTest(owner=owner, subject=subject, revision=revision),
                self.assertRaises(ValueError),
            ):
                profile_proposal(self.calculation, owner, subject, revision)

    def test_profile_rejects_cross_owner_method_metadata(self) -> None:
        calculation = deepcopy(self.calculation)
        artifact = next(
            item
            for item in calculation["artifacts"].values()
            if item["system"] == "bazi"
        )
        calculation["profiles"][artifact["profile_id"]]["owner_user_id"] = "other-owner"
        with self.assertRaises(ValueError):
            profile_proposal(calculation, OWNER, SUBJECT, REVISION)

    def test_profile_keeps_all_real_time_branches_and_resolvable_judgments(
        self,
    ) -> None:
        proposal = profile_proposal(self.multiple, OWNER, SUBJECT, REVISION)
        expected = {item["branch_id"] for item in self.multiple["artifacts"].values()}
        self.assertGreater(len(expected), 1)
        self.assertEqual({row["branch_id"] for row in proposal["branches"]}, expected)
        for branch in proposal["branches"]:
            self.assertEqual(len(branch["judgments"]), 3)
            for judgment in branch["judgments"]:
                artifact = self.multiple["artifacts"][judgment["artifact_id"]]
                self.assertEqual(artifact["branch_id"], branch["branch_id"])
                self.assertEqual(pointer(artifact, judgment["path"]), judgment["value"])

    def test_mutating_profile_proposal_does_not_change_calculation_artifact(
        self,
    ) -> None:
        proposal = profile_proposal(self.calculation, OWNER, SUBJECT, REVISION)
        judgment = proposal["branches"][0]["judgments"][0]
        original = deepcopy(
            pointer(
                self.calculation["artifacts"][judgment["artifact_id"]], judgment["path"]
            )
        )
        judgment["value"]["injected"] = True
        self.assertEqual(
            pointer(
                self.calculation["artifacts"][judgment["artifact_id"]], judgment["path"]
            ),
            original,
        )

    def test_xu_school_rejects_explicit_null_shen_earth(self) -> None:
        with self.assertRaises(ValueError):
            P8ChartAdapter(
                OWNER,
                python=sys.executable,
                p8_options={"command": "xu_7716", "shen_earth": None},
            )

    def test_null_location_reports_missing_input_without_crashing(self) -> None:
        missing = archive()
        missing["user"]["birth"]["location"] = None
        result = self.adapter.calculate(
            missing, "2026-03-20", ["bazi"], REVISION, SUBJECT
        )
        self.assertFalse(result["artifacts"])
        self.assertTrue(result["errors"])
        self.assertEqual(result["errors"][0]["code"], "MISSING_INPUT")

    def test_actual_minute_exact_jingzhe_branches_cover_both_sides(self) -> None:
        birth = archive()["user"]["birth"]
        birth["solar_datetime"] = "2026-03-05 21:59"
        result = self.adapter._branches(birth, SUBJECT, REVISION)
        boundary = datetime(2026, 3, 5, 21, 59)
        points = [datetime.fromisoformat(row["civil_datetime"]) for row in result]
        self.assertTrue(any(point < boundary for point in points))
        self.assertTrue(any(point > boundary for point in points))
        self.assertTrue(all(not row["confirmed_birth_time"] for row in result))

    def test_jie_sensitivity_preserves_declared_interval_metadata(self) -> None:
        birth = archive()["user"]["birth"]
        declared = {"start": "2026-03-05 21:58", "end": "2026-03-05 21:59"}
        birth.update(time_precision="interval", time_interval=declared)
        before = deepcopy(birth)
        result = self.adapter._branches(birth, SUBJECT, REVISION)
        self.assertEqual(birth, before)
        self.assertTrue(result)
        for row in result:
            sampling = row["sampling_range"]
            self.assertEqual(
                sampling["declared_sampling_range"], dict(declared, inclusive=True)
            )
            self.assertEqual(
                sampling["kind"], "calendar_boundary_sensitivity_not_new_birth_fact"
            )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MetaIntegration)
    outcome = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    print(
        json.dumps(
            {
                "tests": outcome.testsRun,
                "failures": len(outcome.failures),
                "errors": len(outcome.errors),
                "skipped": len(outcome.skipped),
                "successful": outcome.wasSuccessful(),
            }
        )
    )
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
