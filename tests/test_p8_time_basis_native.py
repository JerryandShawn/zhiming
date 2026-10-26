"""Real lunar-engine checks for declared clocks, late Zi and physical Jie."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.time_basis import time_basis_candidates  # noqa: E402


class TimeBasisNative(unittest.TestCase):
    def test_urumqi_standard_and_apparent_solar_have_distinct_declared_hours(
        self,
    ) -> None:
        result = time_basis_candidates(
            "1995-03-10", "09:40", {"tz": "Asia/Shanghai", "lon": 87.625}, "clock"
        )
        rows = {row["basis"]: row for row in result["items"]}
        self.assertEqual(rows["standard"]["pillars"]["hour"][1], "巳")
        self.assertEqual(rows["true_solar"]["pillars"]["hour"][1], "辰")
        solar = rows["true_solar"]["solar_time"]
        self.assertEqual(solar["longitude_correction_minutes"], -129.5)
        self.assertLess(
            abs(
                (
                    datetime.fromisoformat(solar["true_solar"])
                    - datetime(1995, 3, 10, 7, 20)
                ).total_seconds()
            ),
            60,
        )
        self.assertIsNone(result["selected_basis"])
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(
            rows["standard"]["calendar_datetime"],
            rows["true_solar"]["calendar_datetime"],
        )
        self.assertEqual((result["model_calls"], result["writes"]), (0, 0))

    def test_same_pillars_deduplicate_bases_but_preserve_all_coordinates(self) -> None:
        result = time_basis_candidates(
            "2010-02-15", "12:00", {"tz": "Asia/Shanghai", "lon": 120}, "standard"
        )
        self.assertEqual(len(result["items"]), 1)
        row = result["items"][0]
        self.assertEqual(row["basis_options"], ["standard", "true_solar"])
        self.assertEqual(len(row["source_variants"]), 2)
        self.assertTrue(result["hour_pillar_stable"] and result["all_pillars_stable"])
        self.assertIsNone(result["selected_basis"])

    def test_late_zi_day_advances_at_23_in_both_time_coordinates(self) -> None:
        place = {"tz": "Asia/Shanghai", "lon": 120}
        rows = []
        for day, clock in (
            ("2010-02-15", "22:59"),
            ("2010-02-15", "23:00"),
            ("2010-02-16", "00:30"),
        ):
            result = time_basis_candidates(day, clock, place, "standard")
            rows.append(
                next(row for row in result["items"] if row["basis"] == "standard")
            )
        self.assertNotEqual(rows[0]["pillars"]["day"], rows[1]["pillars"]["day"])
        self.assertEqual(rows[1]["pillars"]["day"], rows[2]["pillars"]["day"])
        self.assertEqual(rows[1]["pillar_method"]["day_boundary"], "23:00_advances_day")

    def test_true_solar_previous_date_is_retained_without_changing_physical_instant(
        self,
    ) -> None:
        result = time_basis_candidates(
            "2010-01-15", "00:30", {"tz": "Asia/Shanghai", "lon": 80}, "standard"
        )
        rows = {row["basis"]: row for row in result["items"]}
        self.assertTrue(
            rows["true_solar"]["coordinate_datetime"].startswith("2010-01-14")
        )
        self.assertNotEqual(
            rows["standard"]["pillars"]["day"], rows["true_solar"]["pillars"]["day"]
        )
        self.assertEqual(rows["standard"]["utc"], rows["true_solar"]["utc"])

    def test_jie_marker_and_year_month_use_actual_utc_not_shifted_solar_clock(
        self,
    ) -> None:
        result = time_basis_candidates(
            "2026-02-04", "04:02:08", {"tz": "Asia/Shanghai", "lon": 120}, "clock"
        )
        rows = [
            variant for row in result["items"] for variant in row["source_variants"]
        ]
        self.assertTrue(all(row["jie_uncertainty"]["uncertain"] for row in rows))
        self.assertTrue(
            all(row["jie_uncertainty"]["distance_seconds"] == 0 for row in rows)
        )
        self.assertEqual({row["pillars"]["year"] for row in rows}, {"丙午"})
        self.assertEqual({row["pillars"]["month"] for row in rows}, {"庚寅"})
        self.assertTrue(all(not row["legacy_args_compatible"] for row in rows))
        after = time_basis_candidates(
            "2026-02-04", "04:05", {"tz": "Asia/Shanghai", "lon": 120}, "clock"
        )
        self.assertTrue(
            all(not row["jie_uncertainty"]["uncertain"] for row in after["items"])
        )

    def test_standard_clock_engine_coordinates_preserve_the_utc_instant(self) -> None:
        result = time_basis_candidates(
            "1988-07-15", "09:30", {"tz": "Asia/Shanghai", "lon": 104.07}, "unknown"
        )
        variants = [
            variant for row in result["items"] for variant in row["source_variants"]
        ]
        self.assertEqual(len(result["instants"]), 2)
        for row in variants:
            civil = datetime.fromisoformat(row["civil_datetime"])
            actual = datetime.fromisoformat(row["utc"].replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            self.assertEqual(civil - timedelta(hours=row["timezone_offset"]), actual)
            self.assertTrue(row["legacy_args_compatible"])

    def test_unknown_time_samples_centers_and_sides_without_fabricating_known_time(
        self,
    ) -> None:
        result = time_basis_candidates(
            "2010-01-15",
            None,
            {"tz": "Asia/Shanghai", "lon": 120},
            "clock",
            precision="unknown",
        )
        self.assertEqual(len(result["instants"]), 36)
        self.assertTrue(
            result["sampling"].startswith("36_clock_samples_not_continuous")
        )
        self.assertGreaterEqual(len(result["items"]), 12)
        keys = [
            tuple(row["pillars"][key] for key in ("day", "hour", "month"))
            for row in result["items"]
        ]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(row["source_variants"] for row in result["items"]))

    def test_nonexistent_clock_never_becomes_a_guessed_pillar(self) -> None:
        result = time_basis_candidates(
            "1988-04-17", "02:30", {"tz": "Asia/Shanghai", "lon": 120}, "clock"
        )
        self.assertEqual(result["items"], [])
        self.assertEqual(result["instants"][0]["status"], "nonexistent")
        self.assertTrue(result["requires_confirmation"])


if __name__ == "__main__":
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TimeBasisNative)
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
