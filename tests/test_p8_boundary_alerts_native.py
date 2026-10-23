"""Synthetic native lunar/Swiss checks for additive M3 boundary warnings."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.boundary_alerts import boundary_alerts  # noqa: E402
from mingjing_core.adapters.charts.boundary_candidates import (  # noqa: E402
    coordinate_to_utc,
    solar_coordinate,
)
from mingjing_core.adapters.charts.boundary_solar_reference import (  # noqa: E402
    reference_solar_coordinate,
)  # noqa: E402
from mingjing_core.adapters.charts.time_basis import time_basis_candidates  # noqa: E402


def at_coordinate(clock: str, longitude: float = 120) -> dict:
    coordinate = datetime.fromisoformat(clock)
    utc = coordinate_to_utc(coordinate, longitude).replace(microsecond=0)
    civil = (utc + timedelta(hours=8)).replace(tzinfo=None)
    return time_basis_candidates(
        civil.date().isoformat(),
        civil.time().isoformat(),
        {"tz": "Asia/Shanghai", "lon": longitude},
        "standard",
        include_beijing=True,
    )


def selected(rows: list[dict], kind: str) -> dict:
    return next(row for row in rows if row["boundary_kind"] == kind)


class BoundaryAlertsNative(unittest.TestCase):
    def test_ayuan_hour_warning_is_additive_immutable_and_resolvable(self) -> None:
        result = time_basis_candidates(
            "1994-03-12",
            "08:20",
            {"tz": "Asia/Shanghai", "lon": 104.07},
            "clock",
            include_beijing=True,
        )
        before = copy.deepcopy(result)
        rows = boundary_alerts(result)
        self.assertEqual(result, before)
        self.assertEqual([row["boundary_kind"] for row in rows], ["hour_branch"])
        row = rows[0]
        self.assertTrue(row["met"] and row["critical"])
        self.assertEqual(row["threshold_seconds"], 900)
        self.assertLess(row["distance_seconds"], 7 * 60)
        self.assertEqual(row["current_pillars"]["hour"][1], "辰")
        self.assertEqual(
            [value["pillars"]["hour"][1] for value in row["alternatives"]], ["卯", "辰"]
        )
        root = {"time_basis": result}
        for pointer in row["evidence_paths"]:
            value = root
            for token in pointer.lstrip("/").split("/"):
                value = value[int(token)] if isinstance(value, list) else value[token]
            self.assertIsNotNone(value)
        self.assertFalse(row["default_formula_changed"])
        self.assertEqual(boundary_alerts(result), rows)

    def test_ordinary_coordinate_has_no_fabricated_alert(self) -> None:
        rows = boundary_alerts(at_coordinate("2026-03-12T10:00:00"))
        self.assertEqual(rows, [])

    def test_late_zi_boundary_carries_two_kinds_and_actual_day_change(self) -> None:
        rows = boundary_alerts(at_coordinate("2026-03-12T23:05:00"))
        self.assertEqual(
            {row["boundary_kind"] for row in rows}, {"hour_branch", "late_zi_day"}
        )
        row = selected(rows, "late_zi_day")
        before, after = row["alternatives"]
        self.assertNotEqual(before["pillars"]["day"], after["pillars"]["day"])
        self.assertEqual(
            (before["pillars"]["hour"][1], after["pillars"]["hour"][1]), ("亥", "子")
        )
        self.assertTrue(
            all(not value["is_birth_fact"] for value in row["alternatives"])
        )

    def test_midnight_keeps_sect1_day_and_names_sect2_difference(self) -> None:
        row = selected(
            boundary_alerts(at_coordinate("2026-03-13T00:05:00")), "zi_midnight"
        )
        first, second, third, fourth = row["alternatives"]
        self.assertEqual(first["pillars"], third["pillars"])
        self.assertNotEqual(first["pillars"]["day"], second["pillars"]["day"])
        self.assertEqual(third["pillars"], fourth["pillars"])
        self.assertEqual(second["day_boundary"], "00:00_advances_day")

    def test_jie_uses_physical_utc_plus_eight_not_true_solar_clock(self) -> None:
        result = time_basis_candidates(
            "2026-02-04",
            "04:02:08",
            {"tz": "Asia/Shanghai", "lon": 87.625},
            "clock",
            include_beijing=True,
        )
        row = selected(boundary_alerts(result), "jie_month")
        self.assertEqual(row["distance_seconds"], 0)
        self.assertEqual(row["jie"], "立春")
        self.assertEqual(row["threshold_seconds"], 7200)
        self.assertEqual(row["boundary_basis"], "physical_UTC+8")
        before, after = row["alternatives"]
        self.assertEqual(
            (before["pillars"]["year"], after["pillars"]["year"]), ("乙巳", "丙午")
        )
        self.assertNotEqual(before["pillars"]["month"], after["pillars"]["month"])
        self.assertEqual(before["physical_utc"], "2026-02-03T20:02:07Z")

    def test_two_hour_jie_threshold_is_inclusive_not_old_two_minute_band(self) -> None:
        for offset in (-7201, -7200, 7200, 7201):
            civil = datetime(2026, 2, 4, 4, 2, 8) + timedelta(seconds=offset)
            result = time_basis_candidates(
                civil.date().isoformat(),
                civil.time().isoformat(),
                {"tz": "Asia/Shanghai", "lon": 120},
                "standard",
                include_beijing=True,
            )
            kinds = {row["boundary_kind"] for row in boundary_alerts(result)}
            self.assertEqual("jie_month" in kinds, abs(offset) <= 7200)

    def test_previous_date_and_both_dst_folds_retain_instant_identity(self) -> None:
        result = time_basis_candidates(
            "1988-09-11",
            "01:30",
            {"tz": "Asia/Shanghai", "lon": 100},
            "clock",
            include_beijing=True,
        )
        rows = boundary_alerts(result)
        instants = {value["id"]: value["utc"] for value in result["instants"]}
        self.assertEqual(len(instants), 2)
        self.assertTrue(rows)
        self.assertTrue(
            all(row["source_utc"] == instants[row["instant_id"]] for row in rows)
        )

    def test_gap_no_chart_never_becomes_a_guessed_boundary(self) -> None:
        result = time_basis_candidates(
            "1988-04-17",
            "02:30",
            {"tz": "Asia/Shanghai", "lon": 120},
            "clock",
            include_beijing=True,
        )
        self.assertEqual(boundary_alerts(result), [])

    def test_supported_birth_is_preserved_if_sensitivity_crosses_verified_range(
        self,
    ) -> None:
        result = time_basis_candidates(
            "1901-01-01",
            "08:01",
            {"tz": "Asia/Shanghai", "lon": -14},
            "standard",
            include_beijing=True,
        )
        rows = boundary_alerts(result)
        self.assertTrue(rows)
        alternatives = [value for row in rows for value in row["alternatives"]]
        unavailable = [
            value
            for value in alternatives
            if value.get("status", "").startswith("not_computed")
        ]
        self.assertTrue(unavailable)
        self.assertTrue(all(value["pillars"] is None for value in unavailable))
        self.assertTrue(all(row["current_pillars"]["day"] for row in rows))

    def test_reference_preserves_swiss_configuration_and_matches_native_eot(
        self,
    ) -> None:
        import swisseph as swe

        before = swe.get_tid_acc()
        forbidden = (
            "close",
            "set_ephe_path",
            "set_tid_acc",
            "set_delta_t_userdef",
            "set_topo",
            "set_sid_mode",
        )
        with patch.multiple(
            swe,
            **{
                name: lambda *args: self.fail("unexpected Swiss setter")
                for name in forbidden
            },
        ):
            moment = datetime(2026, 2, 11, tzinfo=UTC)
            row = reference_solar_coordinate(moment, 120)
        _, jd_ut1 = swe.utc_to_jd(2026, 2, 11, 0, 0, 0, swe.GREG_CAL)
        self.assertLess(abs(row["eot_minutes"] - swe.time_equ(jd_ut1) * 1440), 1e-7)
        self.assertEqual(swe.get_tid_acc(), before)
        self.assertEqual(row["sun_flags"] & swe.FLG_MOSEPH, swe.FLG_MOSEPH)

    def test_known_research_probe_reports_real_eot_pillar_disagreement(self) -> None:
        kinds = []
        for coordinate, longitude in (
            ("2026-02-11T01:00:00", 87.625),
            ("2026-11-03T23:00:00", 104.07),
        ):
            result = at_coordinate(coordinate, longitude)
            rows = boundary_alerts(result)
            kinds.extend(row["boundary_kind"] for row in rows)
            for row in rows:
                if row["boundary_kind"] == "eot_implementations":
                    self.assertNotEqual(
                        row["current_pillars"], row["alternatives"][0]["pillars"]
                    )
                    self.assertLess(row["distance_seconds"], 5)
                    self.assertIsNone(row["threshold_seconds"])
        self.assertIn("eot_implementations", kinds)

    def test_inverse_is_a_clock_coordinate_not_a_relabelled_utc(self) -> None:
        coordinate = datetime(2026, 3, 12, 7, 0)
        utc = coordinate_to_utc(coordinate, 104.07)
        self.assertLess(
            abs((solar_coordinate(utc, 104.07) - coordinate).total_seconds()), 1e-5
        )
        self.assertEqual(utc.tzinfo, UTC)
        self.assertLess(utc.hour, coordinate.hour)


if __name__ == "__main__":
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryAlertsNative)
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
