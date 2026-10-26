"""Native daily snapshots: real installed calendar, iztro and Swiss calculations."""

from __future__ import annotations

import copy
import json
import os
import platform
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.astro_ephemeris import signed_angle  # noqa: E402
from mingjing_core.adapters.charts.benchmarks.daily_transit_samples import (  # noqa: E402
    sample_natal,
)
from mingjing_core.adapters.charts.benchmarks.handoff_offline import (  # noqa: E402
    offline_runtime,
)
from mingjing_core.adapters.charts.daily_transit import (  # noqa: E402
    daily_transit,
    daily_transit_prepared,
    prepare_natal,
)
from mingjing_core.adapters.charts.tool_evidence import (  # noqa: E402
    content_hash,
    pointer,
)
from mingjing_core.calculations.bazi.elements import ten_god  # noqa: E402


class NativeDailyTransit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.natal = sample_natal()
        cls.prepared = prepare_natal(cls.natal, "2026-10-21")
        cls.results = {
            f"2026-10-{day}": daily_transit_prepared(cls.prepared, f"2026-10-{day}")
            for day in range(21, 28)
        }

    def test_seven_dates_have_noon_beijing_and_the_same_physical_birth(self) -> None:
        for day, result in self.results.items():
            data = result["data"]
            self.assertEqual(data["date"], day)
            self.assertEqual(data["snapshot_at"], day + "T12:00:00+08:00")
            self.assertEqual(data["snapshot_at_utc"], day + "T04:00:00Z")
            self.assertEqual(data["astro"]["natal_at_utc"], "1994-03-12T00:20:00Z")
            self.assertEqual(data["time_basis"]["primary"]["basis"], "true_solar")
            self.assertEqual(data["time_basis"]["comparisons"], [])

    def test_bazi_matches_library_at_noon_and_ten_gods_match_day_master(self) -> None:
        engine = self.prepared.bazi_engine
        for day, result in self.results.items():
            value = datetime.fromisoformat(day).replace(hour=12)
            lunar = engine.Solar.fromYmdHms(
                value.year, value.month, value.day, 12, 0, 0
            ).getLunar()
            expected = (
                lunar.getYearInGanZhiExact(),
                lunar.getMonthInGanZhiExact(),
                lunar.getDayInGanZhiExact2(),
            )
            bazi = result["data"]["bazi"]
            self.assertEqual(
                tuple(
                    bazi["snapshot"][key]["ganzhi"] for key in ("year", "month", "day")
                ),
                expected,
            )
            master = bazi["natal_pillars"]["day"][0]
            for key in ("year", "month", "day"):
                row = bazi["snapshot"][key]
                self.assertEqual(row["stem_ten_god"], ten_god(master, row["ganzhi"][0]))

    def test_all_natal_target_relation_hits_have_real_members_not_transformation(
        self,
    ) -> None:
        for result in self.results.values():
            for hit in result["rule_hits"]:
                context = hit["context"]
                if context["system"] == "bazi" and context["kind"] == "relation":
                    self.assertTrue(context["natal_pillars"])
                    self.assertTrue(context["target_layers"])
                    self.assertFalse(context["transformation_established"])
                    row = pointer(result, hit["evidence_paths"][0])
                    self.assertEqual(context["relation"], row["kind"])
                    self.assertEqual(context["complete"], row.get("complete", True))

    def test_daily_day_pillars_advance_one_sexagenary_step(self) -> None:
        stems, branches = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
        values = [
            result["data"]["bazi"]["snapshot"]["day"]["ganzhi"]
            for result in self.results.values()
        ]
        for left, right in zip(values[:-1], values[1:], strict=True):
            self.assertEqual((stems.index(left[0]) + 1) % 10, stems.index(right[0]))
            self.assertEqual(
                (branches.index(left[1]) + 1) % 12, branches.index(right[1])
            )

    def test_ziwei_actual_layers_each_map_four_unique_transformations(self) -> None:
        for result in self.results.values():
            ziwei = result["data"]["ziwei"]
            self.assertEqual(ziwei["horoscope"]["snapshot_time_index"], 6)
            for layer in ("yearly", "monthly", "daily"):
                rows = ziwei["transformations"][layer]["links"]
                self.assertEqual(
                    [row["mutagen"] for row in rows], ["禄", "权", "科", "忌"]
                )
                self.assertTrue(all(row["status"] == "resolved" for row in rows))
                self.assertEqual(len(ziwei["horoscope"][layer]["mutagen"]), 4)
                for row in rows:
                    location = row["locations"][0]
                    actual = pointer(result, location["star_pointer"])
                    self.assertEqual(actual["name"], location["star_name"])

    def test_astro_aspects_have_actual_separation_inside_explicit_orb(self) -> None:
        for result in self.results.values():
            astro = result["data"]["astro"]
            self.assertEqual(astro["orb_limit_degrees"], 2)
            self.assertEqual(astro["method"]["ephemeris"], "Moshier")
            for row in astro["aspects"]:
                left = astro["transit_planets"][row["from"]]["longitude"]
                right = astro["natal_planets"][row["to"]]["longitude"]
                error = abs(abs(signed_angle(left, right)) - row["angle"])
                self.assertAlmostEqual(error, row["orb_degrees"], places=12)
                self.assertLessEqual(error, 2)

    def test_aliases_hash_resolved_values_and_rule_dependencies(self) -> None:
        for result in self.results.values():
            chart_names = {row["path"]: row["alias"] for row in result["aliases"]["c"]}
            for row in result["aliases"]["c"] + result["aliases"]["r"]:
                self.assertEqual(
                    row["value_sha256"], content_hash(pointer(result, row["path"]))
                )
            for alias in result["aliases"]["r"]:
                hit = pointer(result, alias["path"])
                self.assertTrue(hit["met"])
                self.assertEqual(
                    alias["evidence_aliases"],
                    [chart_names[path] for path in hit["evidence_paths"]],
                )

    def test_fresh_and_reused_natal_give_identical_results_without_mutation(
        self,
    ) -> None:
        original = copy.deepcopy(self.natal)
        result = daily_transit(self.natal, "2026-10-21")
        self.assertEqual(result, self.results["2026-10-21"])
        self.assertEqual(self.natal, original)
        result["data"]["bazi"]["natal_pillars"]["day"] = "甲子"
        self.assertEqual(self.prepared.candidate["pillars"]["day"], "丁酉")

    def test_different_environment_timezone_does_not_change_explicit_snapshot(
        self,
    ) -> None:
        prior = os.environ.get("TZ")
        try:
            for zone in ("UTC", "Asia/Tokyo", "America/New_York"):
                os.environ["TZ"] = zone
                result = daily_transit_prepared(self.prepared, "2026-10-21")
                self.assertEqual(result, self.results["2026-10-21"])
        finally:
            if prior is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = prior

    def test_physical_fold_and_gap_refuse_without_a_guessed_birth(self) -> None:
        for day, time in (("1986-05-04", "02:30"), ("1991-09-15", "01:30")):
            natal = sample_natal()
            natal["birth"].update(date=day, reported_time=time)
            with self.assertRaisesRegex(ValueError, "unconfirmed_physical_instant"):
                prepare_natal(natal, "2026-10-21")

    def test_overseas_birthday_retains_beijing_comparison_without_new_utc(self) -> None:
        natal = sample_natal()
        natal["birth"].update(
            date="2010-01-15",
            reported_time="12:00",
            place={"tz": "America/New_York", "lon": -74, "lat": 40.7},
        )
        prepared = prepare_natal(natal, "2026-10-21")
        self.assertEqual(len(prepared.basis_comparisons), 1)
        comparison = prepared.basis_comparisons[0]
        self.assertEqual(comparison["utc"], prepared.candidate["utc"])
        self.assertTrue(comparison["fields_changed"])
        self.assertEqual(comparison["basis"], "beijing_standard")

    def test_zero_orb_is_a_valid_filter_and_wider_orb_is_a_superset(self) -> None:
        zero = daily_transit_prepared(self.prepared, "2026-10-21", orb_degrees=0)
        wide = daily_transit_prepared(self.prepared, "2026-10-21", orb_degrees=10)
        self.assertTrue(
            all(row["orb_degrees"] == 0 for row in zero["data"]["astro"]["aspects"])
        )
        self.assertGreaterEqual(len(wide["data"]["astro"]["aspects"]), 10)

    def test_equal_bazi_late_zi_can_still_change_ziwei_palaces_at_month_end(
        self,
    ) -> None:
        natal = sample_natal()
        natal["birth"].update(
            date="2000-08-29",
            reported_time="00:00",
            place={"tz": "Asia/Shanghai", "lon": 106, "lat": 30},
        )
        prepared = prepare_natal(natal, "2026-10-21")
        self.assertEqual(len(prepared.basis_comparisons), 1)
        alternate = prepared.basis_comparisons[0]
        self.assertEqual(prepared.candidate["pillars"], alternate["pillars"])
        self.assertNotIn("bazi.pillars", alternate["fields_changed"])
        self.assertIn("ziwei.ming_gong", alternate["fields_changed"])
        self.assertNotEqual(
            prepared.ziwei_natal["ming_gong"], alternate["ziwei_natal"]["ming_gong"]
        )

    def test_effects_and_time_conversion_are_explicit_and_model_free(self) -> None:
        for result in self.results.values():
            self.assertEqual(
                result["effects"],
                {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"},
            )
            local = datetime.fromisoformat(result["data"]["snapshot_at"])
            self.assertEqual(local.utcoffset(), timedelta(hours=8))
            self.assertEqual(local.astimezone(UTC).hour, 4)


if __name__ == "__main__":
    platform.system()
    with offline_runtime():
        result = unittest.TextTestRunner(stream=sys.stderr).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(NativeDailyTransit)
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
