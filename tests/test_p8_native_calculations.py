"""Mandatory Charts-environment checks: real libraries, synthetic inputs, no skips."""

from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from lunar_python import Solar
from lunar_python.util import LunarUtil

from mingjing_core.adapters.charts.adapter import ChartAdapter
from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.p8_worker import calculate, source_hashes
from mingjing_core.adapters.charts.worker import bazi, load_engine
from mingjing_core.calculations.bazi.calendar_layers import calendar_layers, month_command
from mingjing_core.calculations.bazi.elements import BRANCHES, STEMS, ten_god

ROOT = Path(__file__).resolve().parents[1]
ARGS = {"datetime": "2012-05-03 13:18", "lng": 104.07, "tz": 8, "date": "2026-10-17", "gender": "男"}


def archive() -> dict:
    return {
        "owner_user_id": "synthetic-owner",
        "subject_id": "self",
        "user": {
            "gender": "男",
            "birth": {
                "solar_datetime": ARGS["datetime"],
                "timezone_offset": 8,
                "time_precision": "exact",
                "location": {"lng": ARGS["lng"], "lat": 30.67},
            },
        },
    }


class P8NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = calculate(ARGS)
        cls.data = cls.result["data"]
        cls.p8 = cls.data["p8"]
        cls.engine = load_engine("bazi")

    def test_independent_100_ten_god_arithmetic_matches_installed_table(self) -> None:
        for master in STEMS:
            for other in STEMS:
                self.assertEqual(ten_god(master, other), LunarUtil.SHI_SHEN[master + other])

    def test_existing_worker_data_is_identical_except_opt_in_p8(self) -> None:
        self.assertEqual({key: value for key, value in self.data.items() if key != "p8"}, bazi(ARGS)["data"])
        self.assertNotIn("p8", bazi(ARGS)["data"])

    def test_exact_start_age_preserves_existing_sect1_result(self) -> None:
        luck = self.p8["decade_luck"]
        self.assertEqual(luck["start_age"], {"years": 0, "months": 7, "days": 10, "hours": 0})
        self.assertEqual(luck["nominal_start_at"], "2012-12-13T13:18:00+08:00")
        self.assertEqual(len(luck["decades"]), 10)
        for row, old in zip(luck["decades"], self.data["dayun"], strict=True):
            self.assertEqual(row["ganzhi"], old["ganzhi"])
            self.assertEqual(row["legacy_start_age"], old["start_age"])
            self.assertEqual(row["legacy_start_year"], old["start_year"])
        for left, right in zip(luck["decades"][:-1], luck["decades"][1:], strict=True):
            self.assertEqual(left["nominal_end_exclusive"], right["nominal_start_at"])

    def test_male_and_female_direction_and_aliases_preserved(self) -> None:
        self.assertTrue(self.p8["decade_luck"]["forward"])
        female = calculate(dict(ARGS, gender="女"))["data"]["p8"]["decade_luck"]
        self.assertFalse(female["forward"])
        for gender in ("male", "M", "m", "1"):
            self.assertEqual(calculate(dict(ARGS, gender=gender))["data"]["p8"]["decade_luck"], self.p8["decade_luck"])

    def test_twelve_exact_jie_months_cover_one_lichun_year(self) -> None:
        layer = self.p8["calendar_layers"]
        self.assertEqual(layer["year"]["ganzhi"], "丙午")
        self.assertEqual(
            [row["ganzhi"] for row in layer["months"]],
            ["庚寅", "辛卯", "壬辰", "癸巳", "甲午", "乙未", "丙申", "丁酉", "戊戌", "己亥", "庚子", "辛丑"],
        )
        self.assertEqual(layer["months"][0]["period_start"], layer["year"]["period_start"])
        self.assertEqual(layer["months"][-1]["period_end_exclusive"], layer["year"]["period_end_exclusive"])
        for left, right in zip(layer["months"][:-1], layer["months"][1:], strict=True):
            self.assertEqual(left["period_end_exclusive"], right["period_start"])

    def test_every_jie_month_boundary_before_and_after(self) -> None:
        for row in self.p8["calendar_layers"]["months"]:
            boundary = datetime.fromisoformat(row["period_start"]).replace(tzinfo=None)

            def month_at(point: datetime) -> str:
                return (
                    Solar.fromYmdHms(point.year, point.month, point.day, point.hour, point.minute, point.second)
                    .getLunar()
                    .getMonthInGanZhiExact()
                )

            self.assertNotEqual(month_at(boundary - timedelta(seconds=1)), row["ganzhi"])
            self.assertEqual(month_at(boundary), row["ganzhi"])

    def test_target_day_and_month_match_unchanged_v3(self) -> None:
        target = self.p8["calendar_layers"]["day"]
        self.assertEqual(target["day"]["ganzhi"], self.data["day"]["day_ganzhi"])
        self.assertEqual(target["month"]["ganzhi"], self.data["target_month"]["ganzhi"])
        self.assertEqual(target["year"]["ganzhi"], self.data["target_year"]["ganzhi"])
        self.assertEqual(target["day"]["stem_ten_god"], "比肩")
        self.assertEqual(target["hour"]["ganzhi"][1], "午")
        self.assertTrue(target["hour_is_snapshot_only"])

    def test_january_target_preserves_previous_jie_year(self) -> None:
        natal = {key: value["ganzhi"] for key, value in self.data["pillars"].items()}
        layers = calendar_layers(self.engine, 2026, "2026-01-01", natal)
        self.assertEqual(layers["day"]["year"]["ganzhi"], "乙巳")
        self.assertEqual(layers["year"]["ganzhi"], "丙午")
        self.assertNotEqual(layers["day"]["month"]["ganzhi"], layers["months"][0]["ganzhi"])

    def test_command_uses_same_instant_calendar_not_solar_corrected_clock(self) -> None:
        value = self.p8["month_command"]
        self.assertEqual(value["calendar_birth_at"], "2012-05-03T13:18:00+08:00")
        self.assertEqual(value["commanding_stem"], "戊")
        self.assertNotEqual(value["calendar_birth_at"][:16], self.data["corrected_time"][:16])
        same = calculate(dict(ARGS, datetime="2012-05-03 05:18", tz=0))["data"]["p8"]
        self.assertEqual(same["month_command"], value)
        self.assertEqual(same["decade_luck"], self.p8["decade_luck"])

    def test_command_changes_at_jie_with_actual_second_boundary(self) -> None:
        layer = self.p8["calendar_layers"]["months"][0]
        boundary = datetime.fromisoformat(layer["period_start"]).replace(tzinfo=None)
        for seconds in (0, 1, 4 * 86400):
            value = month_command(self.engine, boundary + timedelta(seconds=seconds), "寅", "甲")
            self.assertEqual(value["commanding_stem"], "戊")
            self.assertAlmostEqual(value["elapsed_days"], seconds / 86400, places=8)

    def test_source_fingerprint_contains_rules_tables_and_no_absolute_paths(self) -> None:
        hashes = source_hashes()
        self.assertGreaterEqual(len(hashes), 12)
        for name, digest in hashes.items():
            self.assertFalse(Path(name).is_absolute())
            actual = hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            self.assertEqual(digest, actual)

    def test_opt_in_adapter_json_pointers_and_old_artifact_data(self) -> None:
        arc = archive()
        before = copy.deepcopy(arc)
        new = P8ChartAdapter("synthetic-owner", python=sys.executable).calculate(arc, ARGS["date"], ["bazi"], 1, "self")
        old = ChartAdapter("synthetic-owner", python=sys.executable).calculate(arc, ARGS["date"], ["bazi"], 1, "self")
        self.assertEqual(new["errors"], [])
        self.assertEqual(old["errors"], [])
        new_data = next(iter(new["artifacts"].values()))["data"]
        self.assertEqual(
            {key: value for key, value in new_data.items() if key != "p8"},
            next(iter(old["artifacts"].values()))["data"],
        )
        self.assertEqual(arc, before)
        for feature in new["features"].values():
            value = new["artifacts"][feature["artifact_id"]]
            for key in feature["path"].lstrip("/").split("/"):
                value = value[key]
            self.assertEqual(feature["value"], value)
        self.assertEqual(
            len([row for row in new["features"].values() if row["feature_key"].startswith("bazi.p8.")]), 13
        )

    def test_unknown_time_finite_samples_and_different_day_master_survive(self) -> None:
        arc = archive()
        birth = arc["user"]["birth"]
        birth.update(time_precision="unknown", solar_date="2012-05-03")
        # Synthetic longitude 60 avoids the known v3 Si hidden-order refusal,
        # while retaining a local-mean-solar previous-day sample at 00:00 civil.
        birth["location"]["lng"] = 60
        result = P8ChartAdapter("synthetic-owner", python=sys.executable).calculate(
            arc, ARGS["date"], ["bazi"], 1, "self"
        )
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["branches"]), 5)
        self.assertTrue(all(not branch["confirmed_birth_time"] for branch in result["branches"]))
        features = [row for row in result["features"].values() if row["feature_key"] == "bazi.p8.ten_gods"]
        self.assertTrue(all(row["stability"] == "conditional" for row in features))
        self.assertGreater(len({row["value"]["day_master"] for row in features}), 1)
        self.assertTrue(all(branch["coverage"] == "sampled_not_continuous" for branch in result["branches"]))

    def test_v3_si_failure_remains_and_named_entry_records_legacy_bridge(self) -> None:
        arc = archive()
        arc["user"]["birth"].update(time_precision="unknown", solar_date="2012-05-03")
        new = P8ChartAdapter("synthetic-owner", python=sys.executable).calculate(arc, ARGS["date"], ["bazi"], 1, "self")
        old = ChartAdapter("synthetic-owner", python=sys.executable).calculate(arc, ARGS["date"], ["bazi"], 1, "self")
        self.assertEqual(new["errors"], [])
        self.assertEqual(len(old["errors"]), 1)
        self.assertEqual(len(old["artifacts"]), 4)
        self.assertEqual(len(new["artifacts"]), 5)
        bridged = [row["data"]["p8"] for row in new["artifacts"].values() if "legacy_bridge" in row["data"]["p8"]]
        self.assertEqual(len(bridged), 1)
        self.assertIn(["丙", "庚", "戊"], bridged[0]["engine_hidden_stems_before_legacy_derivation"].values())
        self.assertTrue(any(row["stability"] == "conditional" for row in new["features"].values()))

    def test_owner_scope_is_checked_before_opt_in_worker(self) -> None:
        adapter = P8ChartAdapter("other-owner", python="must-not-run")
        result = adapter.calculate(archive(), ARGS["date"], ["bazi"], 1, "self")
        self.assertEqual(result["errors"][0]["code"], "AUTH_SCOPE_ERROR")

    def test_day_pillar_empty_stems_match_all_sixty_native_decades(self) -> None:
        from mingjing_core.calculations.bazi.stars import auxiliary_stars

        for index in range(60):
            ganzhi = STEMS[index % 10] + BRANCHES[index % 12]
            natal = dict(year="甲子", month="丙寅", day=ganzhi, hour="甲子")
            result = next(row for row in auxiliary_stars(natal)["markers"] if row["name"] == "空亡")
            self.assertEqual("".join(result["target_branches"]), LunarUtil.getXunKong(ganzhi))


if __name__ == "__main__":
    unittest.main()
