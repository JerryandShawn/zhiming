"""Actual offline daily integration for the date-ranking adapter."""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts import daily_transit as daily_module  # noqa: E402
from mingjing_core.adapters.charts.tool_evidence import (  # noqa: E402
    content_hash,
    pointer,
)
from mingjing_core.adapters.charts.window_search import window_search  # noqa: E402

NATAL = {
    "owner_user_id": "synthetic-owner-ayuan",
    "subject_id": "synthetic-subject-ayuan",
    "revision": 1,
    "operation_id": "synthetic-window-ayuan-20261021",
    "birth": {
        "date": "1994-03-12",
        "reported_time": "08:20",
        "gender": "男",
        "clock_basis": "clock",
        "precision": "reported",
        "place": {"tz": "Asia/Shanghai", "lon": 104.07, "lat": 30.67},
    },
}
RANGE = {"start_date": "2026-10-21", "end_date": "2026-10-27"}


class WindowSearchNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        before = copy.deepcopy(NATAL)
        cls.result = window_search(NATAL, RANGE, "签约")
        assert before == NATAL

    def test_seven_real_days_have_transparent_signed_scores_and_sourced_aliases(
        self,
    ) -> None:
        result = self.result
        self.assertEqual(len(result["data"]["candidates"]), 7)
        self.assertEqual(result["data"]["range"]["day_count"], 7)
        self.assertTrue(result["rule_hits"])
        for row in result["data"]["candidates"]:
            links = row["positive_hits"] + row["negative_hits"] + row["neutral_hits"]
            self.assertEqual(row["score"], sum(link["contribution"] for link in links))
            for link in links:
                hit = result["rule_hits"][link["rule_hit_index"]]
                self.assertEqual(hit["contribution"], link["contribution"])
                self.assertEqual(hit["date"], row["date"])
                self.assertTrue(hit["school"] and hit["source"] and hit["met"])
        for group in ("c", "r"):
            for alias in result["aliases"][group]:
                self.assertEqual(
                    content_hash(pointer(result, alias["path"])), alias["value_sha256"]
                )

    def test_observations_equal_an_independently_requested_actual_day(self) -> None:
        day = daily_module.daily_transit(NATAL, "2026-10-21")
        observed = [
            row
            for row in self.result["data"]["observations"]
            if row["date"] == "2026-10-21"
        ]
        self.assertEqual(len(observed), len(day["rule_hits"]))
        for row in observed:
            self.assertEqual(row["daily_document_id"], day["document_id"])
            self.assertEqual(
                row["daily_hit"], day["rule_hits"][row["daily_rule_index"]]
            )
            for fact in row["facts"]:
                self.assertEqual(fact["value"], pointer(day, fact["path"]))

    def test_default_calculation_prepares_natal_only_once(self) -> None:
        with patch.object(
            daily_module, "prepare_natal", wraps=daily_module.prepare_natal
        ) as prepare:
            actual = window_search(
                NATAL, {"start_date": "2026-10-21", "end_date": "2026-10-22"}, "面试"
            )
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(len(actual["data"]["candidates"]), 2)

    def test_all_six_purposes_use_real_calculations_and_explicit_scope(self) -> None:
        for purpose in ("签约", "面试", "搬家", "出行", "表白", "开业"):
            actual = window_search(
                NATAL, {"start_date": "2026-10-21", "end_date": "2026-10-21"}, purpose
            )
            self.assertEqual(actual["data"]["purpose"], purpose)
            self.assertEqual(actual["scope"]["subject_id"], NATAL["subject_id"])
            self.assertEqual(actual["effects"]["model_calls"], 0)
            self.assertEqual(actual["effects"]["writes"], 0)

    def test_host_timezone_environment_does_not_change_explicit_date_results(
        self,
    ) -> None:
        with patch.dict(os.environ, {"TZ": "UTC"}):
            left = window_search(
                NATAL, {"start_date": "2026-10-21", "end_date": "2026-10-21"}, "出行"
            )
        with patch.dict(os.environ, {"TZ": "Asia/Tokyo"}):
            right = window_search(
                NATAL, {"start_date": "2026-10-21", "end_date": "2026-10-21"}, "出行"
            )
        self.assertEqual(left, right)

    def test_maximum_31_day_page_stays_below_existing_worker_size_limit(self) -> None:
        result = window_search(
            NATAL, {"start_date": "2026-10-21", "end_date": "2026-11-20"}, "签约"
        )
        self.assertEqual(result["data"]["pagination"]["returned"], 31)
        self.assertLess(
            len(json.dumps(result, ensure_ascii=False).encode("utf8")), 8_000_000
        )
        self.assertEqual(result["data"]["pagination"]["has_more"], False)


if __name__ == "__main__":
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(WindowSearchNative)
    )
    print(
        json.dumps(
            {
                "tests": result.testsRun,
                "successful": result.wasSuccessful(),
                "skipped": len(result.skipped),
            }
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
