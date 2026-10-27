"""Review 24: optional book table and installed late-Zi boundary evidence."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.worker import load_engine  # noqa: E402
from mingjing_core.adapters.charts.ziwei_flying import palace_flying_transformations  # noqa: E402


def chart(value: str):
    engine = load_engine("ziwei")
    astro, coordinate = engine.build(datetime.fromisoformat(value), 0, "女", 0)
    return astro, engine.natal(astro, coordinate)


def major_positions(data: dict) -> dict[str, int]:
    return {star["name"]: palace["index"] for palace in data["palaces"] for star in palace["major"]}


class NativeReview24(unittest.TestCase):
    def test_late_zi_date_and_month_boundary_are_not_blanket_same_as_next_day(self) -> None:
        _, previous = chart("2000-08-16T22:59:00")
        late_astro, late = chart("2000-08-16T23:00:00")
        next_astro, following = chart("2000-08-17T00:00:00")
        self.assertEqual(previous["method"]["hour_index"], 11)
        self.assertEqual(late["method"]["hour_index"], 12)
        self.assertEqual(following["method"]["hour_index"], 0)
        self.assertNotEqual(previous["lunar_date"], late["lunar_date"])
        self.assertEqual(late["lunar_date"], following["lunar_date"])
        self.assertNotEqual(late_astro.lunar_date, next_astro.lunar_date)
        self.assertEqual(late["ming_gong"], following["ming_gong"])
        self.assertEqual(major_positions(late), major_positions(following))
        _, late_end = chart("2000-08-28T23:00:00")
        _, next_month = chart("2000-08-29T00:00:00")
        self.assertEqual(late_end["lunar_date"], next_month["lunar_date"])
        self.assertEqual(major_positions(late_end), major_positions(next_month))
        self.assertEqual((late_end["ming_gong"], next_month["ming_gong"]), ("申", "酉"))

    def test_quanshu_uses_actual_tianfu_without_reconfiguring_engine(self) -> None:
        _, data = chart("1992-08-16T03:00:00")
        before = copy.deepcopy(data)
        default = palace_flying_transformations(data)
        optional = palace_flying_transformations(data, school="quanshu")
        self.assertEqual(data, before)
        self.assertEqual(optional["natal"], default["natal"])
        self.assertEqual([row["star"] for row in optional["natal"]["links"] if row["mutagen"] == "科"], ["左辅"])
        for edge in optional["edges"]:
            if edge["source"]["ganzhi"][0] == "壬" and edge["mutagen"] == "科":
                self.assertEqual(edge["star"], "天府")
                target = edge["locations"][0]["palace_index"]
                self.assertEqual(target, major_positions(data)["天府"])
        self.assertTrue(optional["complete"])
        self.assertEqual(palace_flying_transformations(data)["table_id"], "iztro")


if __name__ == "__main__":
    result = unittest.TextTestRunner(stream=sys.stderr).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(NativeReview24)
    )
    print(json.dumps({"tests": result.testsRun, "successful": result.wasSuccessful(), "skipped": len(result.skipped)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
