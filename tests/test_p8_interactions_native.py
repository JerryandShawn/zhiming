"""Native Charts-only checks and synthetic crosschecks; prints no private data."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.interactions_bazi import bazi_interactions  # noqa: E402
from mingjing_core.adapters.charts.interactions_transits import transit_windows  # noqa: E402
from mingjing_core.adapters.charts.interactions_ziwei import yearly_mutagen_links  # noqa: E402
from mingjing_core.adapters.charts.worker import load_engine, ziwei  # noqa: E402

ARGS = {
    "datetime": "2012-05-03 13:18",
    "lng": 104.07,
    "lat": 30.67,
    "tz": 8,
    "gender": "男",
    "date": "2026-10-18",
}


class InteractionsNative(unittest.TestCase):
    def test_all_exposed_ten_gods_against_lunar_engine(self) -> None:
        engine = load_engine("bazi")
        stems = "甲乙丙丁戊己庚辛壬癸"
        for master in stems:
            natal = {
                "year": "甲子",
                "month": "丙寅",
                "day": master + ("子" if stems.index(master) % 2 == 0 else "丑"),
                "hour": "丁卯",
            }
            for other in stems:
                target = other + ("辰" if stems.index(other) % 2 == 0 else "巳")
                result = bazi_interactions(natal, {"yearly": target})
                self.assertEqual(
                    result["nodes"][-1]["stem_ten_god"],
                    engine.LunarUtil.SHI_SHEN[master + other],
                )

    def test_ziwei_all_four_links_match_installed_engine(self) -> None:
        data = ziwei(ARGS)["data"]
        result = yearly_mutagen_links(data)
        self.assertTrue(result["complete"])
        actual = data["horoscope"]["yearly"]["mutagen_links"]
        self.assertEqual(len(actual), 4)
        for row, reference in zip(result["links"], actual, strict=True):
            self.assertEqual(row["star"], reference["star"])
            self.assertEqual(
                row["locations"][0]["palace_index"], reference["palace_index"]
            )
            self.assertEqual(
                row["locations"][0]["yearly_palace"], reference["scope_palace"]
            )

    def test_sun_zero_longitude_occurs_on_public_hko_equinox_date(self) -> None:
        result = transit_windows(
            {"reference_zero": 0},
            "2026-03-16T00:00:00Z",
            "2026-03-25T00:00:00Z",
            moving_bodies=("太阳",),
        )
        row = next(row for row in result["windows"] if row["aspect"] == "合相")
        exact = datetime.fromisoformat(row["exact_at"][0].replace("Z", "+00:00"))
        self.assertEqual(exact.strftime("%Y-%m-%d"), "2026-03-20")
        self.assertFalse(row["start_clipped"] or row["end_clipped"])
        self.assertEqual([phase["phase"] for phase in row["phases"]], ["入相", "出相"])
        self.assertEqual(result["returned_flags"]["太阳"], [260])

    def test_moon_six_hour_search_agrees_with_finer_grid(self) -> None:
        args = ({"reference": 359.8}, "2026-03-01T00:00:00Z", "2026-03-31T00:00:00Z")
        coarse = transit_windows(*args, moving_bodies=("月亮",), step_hours=6)
        fine = transit_windows(*args, moving_bodies=("月亮",), step_hours=1)
        self.assertEqual(len(coarse["windows"]), len(fine["windows"]))
        for left, right in zip(coarse["windows"], fine["windows"], strict=True):
            self.assertEqual(
                (left["aspect"], left["oriented_offset"]),
                (right["aspect"], right["oriented_offset"]),
            )
            for field in ("window_start", "window_end"):
                delta = datetime.fromisoformat(
                    left[field].replace("Z", "+00:00")
                ) - datetime.fromisoformat(right[field].replace("Z", "+00:00"))
                self.assertLessEqual(abs(delta.total_seconds()), 3)

    def test_mercury_retrograde_retains_multiple_exact_passes(self) -> None:
        result = transit_windows(
            {"reference": 225},
            "2026-10-01T00:00:00Z",
            "2026-12-10T00:00:00Z",
            moving_bodies=("水星",),
        )
        rows = [row for row in result["windows"] if row["aspect"] == "合相"]
        self.assertEqual(sum(len(row["exact_at"]) for row in rows), 3)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InteractionsNative)
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
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
