"""Named-method boundaries and actual Charts-process integration."""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timedelta

from mingjing_core.adapters.charts.jie_uncertainty import probe
from mingjing_core.adapters.charts.named_bazi import hidden_for, named_command, named_stars, options
from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.p8_worker import calculate
from mingjing_core.adapters.charts.worker import bazi, load_engine

ARGS = {"datetime": "2012-05-03 13:18", "lng": 104.07, "tz": 8, "date": "2026-10-18", "gender": "男"}


class NamedMethodsTests(unittest.TestCase):
    def test_two_named_tables_and_exact_half_open_segments(self) -> None:
        default, other = options(), options({"command": "xu_7716", "shen_earth": "戊"})
        for days, expected in ((0, "戊"), (4.99999, "戊"), (5, "丙"), (10, "甲"), (32, "甲")):
            self.assertEqual(named_command("寅", days, "甲", default)["commanding_stem"], expected)
        for days, expected in ((6.99, "戊"), (7, "丙"), (14, "甲")):
            self.assertEqual(named_command("寅", days, "甲", other)["commanding_stem"], expected)
        self.assertEqual(hidden_for(default)["巳"], "丙庚戊")
        self.assertEqual(hidden_for(default)["辰"], "戊壬乙")
        self.assertEqual(hidden_for(other)["辰"], "戊癸乙")

    def test_source_ambiguity_requires_explicit_choice_and_unknown_options_fail(self) -> None:
        for value in (
            {"command": "xu_7716"},
            {"command": "xu_7716", "shen_earth": None},
            {"command": "unknown"},
            {"invented": "yes"},
        ):
            with self.assertRaises(ValueError):
                options(value)
        first = options({"command": "xu_7716", "shen_earth": "戊"})
        second = options({"command": "xu_7716", "shen_earth": "己"})
        self.assertEqual(named_command("申", 0, "甲", first)["commanding_stem"], "戊")
        self.assertEqual(named_command("申", 0, "甲", second)["commanding_stem"], "己")
        for days in (-1, float("inf"), float("nan"), True):
            with self.assertRaises(ValueError):
                named_command("寅", days, "甲", options())

    def test_auxiliary_defaults_and_explicit_alternatives(self) -> None:
        pillars = dict(year="甲子", month="丙寅", day="乙卯", hour="庚辰")
        default = named_stars(pillars, options())
        other = named_stars(pillars, options({"tianyi": "cao_yang", "blade": "yuanhai_yin_included"}))
        for result, tianyi, blade in ((default, ["子", "申"], []), (other, ["申"], ["辰"])):
            rows = {row["name"]: row for row in result["markers"] if row["name"] in ("天乙贵人", "羊刃")}
            self.assertEqual(rows["天乙贵人"]["target_branches"], tianyi)
            self.assertEqual(rows["羊刃"]["target_branches"], blade)

    def test_named_calculation_does_not_change_legacy_worker_fields(self) -> None:
        before = copy.deepcopy(ARGS)
        value = calculate(ARGS)["data"]
        self.assertEqual({key: item for key, item in value.items() if key != "p8"}, bazi(ARGS)["data"])
        self.assertEqual(ARGS, before)
        self.assertEqual(value["p8"]["climate"]["collation_status"], "未经原刊校勘")
        self.assertIn("project_method_v1", value["p8"]["strength"]["editorial_status"])
        self.assertEqual(value["p8"]["patterns"]["establishment"], "candidate_only")

    def test_jie_band_inclusive_and_same_instant_timezone_equivalence(self) -> None:
        engine = load_engine("bazi")
        boundary = datetime.fromisoformat(
            engine.Solar.fromYmd(2026, 2, 5).getLunar().getPrevJie().getSolar().toYmdHms()
        )
        floor = boundary.replace(second=0)
        for offset in (-1, 0, 1):
            point = floor + timedelta(minutes=offset)
            value = probe(engine, point.strftime("%Y-%m-%d %H:%M"), 8)
            self.assertIsNotNone(value)
            utc = probe(engine, (point - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"), 0)
            self.assertEqual(value["calendar_boundary"], utc["calendar_boundary"])
        self.assertIsNone(probe(engine, (floor + timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M"), 8))

    def test_adapter_jie_generates_two_sides_and_resolvable_features(self) -> None:
        engine = load_engine("bazi")
        boundary = engine.Solar.fromYmd(2026, 2, 5).getLunar().getPrevJie().getSolar().toYmdHms()[:16]
        archive = {
            "user": {
                "gender": "男",
                "birth": {
                    "solar_datetime": boundary,
                    "timezone_offset": 8,
                    "time_precision": "exact",
                    "location": {"lng": 120, "lat": 30},
                },
            }
        }
        original = copy.deepcopy(archive)
        result = P8ChartAdapter("synthetic", python=sys.executable).calculate(
            archive, "2026-10-18", ["bazi"], 0, "self"
        )
        self.assertEqual(result["errors"], [])
        self.assertGreaterEqual(len(result["branches"]), 2)
        months = {row["data"]["pillars"]["month"]["ganzhi"] for row in result["artifacts"].values()}
        self.assertEqual(len(months), 2)
        self.assertTrue(all(not row["confirmed_birth_time"] for row in result["branches"]))
        self.assertTrue(all(row["coverage"] == "sampled_not_continuous" for row in result["branches"]))
        self.assertEqual(archive, original)
        for feature in result["features"].values():
            value = result["artifacts"][feature["artifact_id"]]
            for step in feature["path"].lstrip("/").split("/"):
                value = value[step]
            self.assertEqual(feature["value"], value)


if __name__ == "__main__":
    unittest.main()
