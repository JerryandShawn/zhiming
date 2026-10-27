"""Short, synthetic-only real Charts grid/cache boundary checks; no model calls."""

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lunar_python import Solar  # noqa: E402

from mingjing_core.adapters.charts.rectification_workbench.chart_grid import (  # noqa: E402
    synthetic_chart_grid,
)
from mingjing_core.adapters.charts.rectification_workbench.contracts import (  # noqa: E402
    rules,
)
from mingjing_core.adapters.charts.rectification_workbench.signals import (  # noqa: E402
    precompute,
)
from mingjing_core.adapters.charts.rules import evaluate_rules  # noqa: E402


def request() -> dict:
    return {
        "owner_user_id": "synthetic-grid-owner",
        "subject_id": "synthetic-grid-subject",
        "revision": 1,
        "operation_id": "synthetic-grid-operation",
        "as_of_date": "2026-10-18",
        "birth": {
            "date": "2019-10-18",
            "reported_time": "08:00",
            "precision": "reported",
            "gender": "男",
            "place": {"tz": "Asia/Shanghai", "lon": 120},
            "clock_basis": "standard",
        },
    }


def at(value: str):
    point = datetime.fromisoformat(value).replace(tzinfo=None)
    return Solar.fromYmdHms(
        point.year, point.month, point.day, point.hour, point.minute, point.second
    ).getLunar()


def pointer(value: dict, path: str):
    for part in path.removeprefix("/").split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


class WorkbenchGridNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input = request()
        cls.before = deepcopy(cls.input)
        cls.contexts = synthetic_chart_grid(cls.input, basis="standard")
        cls.scope = ("synthetic-grid-owner", "synthetic-grid-subject", 1)
        cls.cache = precompute(
            cls.contexts, birth_year=2019, as_of_year=2026, scope=cls.scope
        )

    def test_twelve_midpoints_match_real_calendar_and_declared_pillars(self) -> None:
        self.assertEqual(len(self.contexts), 12)
        self.assertEqual(len({row["id"] for row in self.contexts}), 12)
        for hour, row in zip(range(0, 24, 2), self.contexts, strict=True):
            self.assertEqual(row["label"], f"standard:{hour:02}:00")
            basis = row["time_basis"]
            self.assertEqual(
                basis["coordinate_datetime"], f"2019-10-18T{hour:02}:00:00"
            )
            lunar = at(basis["calendar_datetime"])
            eight = at(basis["coordinate_datetime"]).getEightChar()
            eight.setSect(1)
            expected = {
                "year": lunar.getYearInGanZhiExact(),
                "month": lunar.getMonthInGanZhiExact(),
                "day": eight.getDay(),
                "hour": eight.getTime(),
            }
            self.assertEqual(row["pillars"], expected)
            self.assertEqual(
                {key: value["ganzhi"] for key, value in row["data"]["pillars"].items()},
                expected,
            )
            self.assertIn("not continuous unknown-time coverage", row["grid_limit"])

    def test_p8_and_u12_use_the_same_natal_pillars_and_actual_rule_engine(self) -> None:
        for row in self.contexts:
            p8 = row["p8"]
            self.assertEqual(p8["ten_gods"]["day_master"], row["pillars"]["day"][0])
            graph = p8["time_interactions"]
            natal = {
                node["id"][6:]: node["ganzhi"]
                for node in graph["nodes"]
                if node["id"].startswith("natal.")
            }
            self.assertEqual(natal, row["pillars"])
            assessed = evaluate_rules(row["data"], graph=graph)
            self.assertEqual(p8["rule_hits"], assessed["rule_hits"])
            self.assertEqual(p8["rule_assessments"], assessed["assessments"])
            self.assertTrue(all(hit["met"] is True for hit in p8["rule_hits"]))

    def test_ziwei_is_separate_with_contiguous_clock_clipped_annual_pieces(
        self,
    ) -> None:
        for row in self.contexts:
            column = row["ziwei_column"]
            self.assertFalse(column["scored"])
            self.assertEqual(set(column["annual"]), {"2025", "2026"})
            for year, pieces in column["annual"].items():
                self.assertEqual(pieces[0]["start"], year + "-01-01")
                expected_end = "2026-01-01" if year == "2025" else "2026-10-19"
                self.assertEqual(pieces[-1]["end_exclusive"], expected_end)
                for index, piece in enumerate(pieces):
                    self.assertLessEqual(piece["end_exclusive"], "2026-10-19")
                    self.assertLessEqual(piece["start"], piece["sample_date"])
                    self.assertLess(piece["sample_date"], piece["end_exclusive"])
                    self.assertTrue(piece["not_event_date"])
                    self.assertIn("mutagen", piece["yearly"])
                    if index:
                        self.assertEqual(
                            pieces[index - 1]["end_exclusive"], piece["start"]
                        )

    def test_cache_covers_all_registered_signals_and_binds_clock_metadata(self) -> None:
        cache = self.cache
        expected = {
            item["signal"]
            for mappings in rules()["event_rules"].values()
            for item in mappings
        }
        self.assertEqual(set(cache.signal_ids), expected)
        self.assertIn("rule:u12-palace-day-clash-combine", expected)
        self.assertEqual(cache.years, (2025, 2026))
        self.assertEqual(cache.scope, self.scope)
        self.assertEqual(len(cache.values), 2)
        self.assertTrue(all(len(year) == 12 for year in cache.values))
        self.assertTrue(
            all(len(row) == len(expected) for year in cache.values for row in year)
        )
        columns = json.loads(cache.columns_json)
        self.assertEqual(set(columns), set(cache.candidate_ids))
        self.assertTrue(
            all(row["as_of_date"] == "2026-10-18" for row in columns.values())
        )
        self.assertTrue(
            all(row["engine_versions"]["lunar-python"] for row in columns.values())
        )

    def test_annual_graphs_preserve_physical_jie_and_resolvable_evidence(self) -> None:
        evidence = json.loads(self.cache.evidence_json)
        for yearly in evidence.values():
            for ident, detail in yearly.items():
                for piece in detail["pieces"]:
                    point = piece["sample_at"]
                    self.assertLess(
                        datetime.fromisoformat(point),
                        datetime.fromisoformat("2026-10-19T00:00+08:00"),
                    )
                    graph = piece["data"]["p8"]["time_interactions"]
                    annual = next(
                        node for node in graph["nodes"] if node["id"] == "target.yearly"
                    )
                    self.assertEqual(annual["ganzhi"], at(point).getYearInGanZhiExact())
                for signal in detail["signals"].values():
                    for references in signal["pieces"]:
                        for reference in references:
                            self.assertEqual(
                                reference["alias_status"],
                                "unregistered_mainline_alias_required",
                            )
                            self.assertTrue(reference["evidence_paths"])
                            for path in reference["evidence_paths"]:
                                self.assertIn(ident, path)
                                self.assertIsInstance(pointer(evidence, path), dict)

    def test_scores_use_only_bazi_signals_while_ziwei_remains_visible(self) -> None:
        self.assertTrue(all("ziwei" not in signal for signal in self.cache.signal_ids))
        tables = self.cache.score_tables()
        self.assertEqual(set(tables), set(rules()["event_rules"]))
        for rows in tables.values():
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(len(row) == 12 for row in rows))
        columns = json.loads(self.cache.columns_json)
        self.assertTrue(all("ziwei_column" in row for row in columns.values()))
        self.assertTrue(
            all(row["ziwei_column"]["scored"] is False for row in columns.values())
        )

    def test_owner_subject_and_revision_mismatches_fail_before_precompute(self) -> None:
        for field, changed in (
            ("owner_user_id", "different-owner"),
            ("subject_id", "synthetic-different-subject"),
            ("revision", 2),
        ):
            with self.subTest(field=field):
                contexts = [dict(row) for row in self.contexts]
                contexts[0][field] = changed
                with self.assertRaisesRegex(ValueError, "scope_mismatch"):
                    precompute(
                        contexts, birth_year=2019, as_of_year=2026, scope=self.scope
                    )

    def test_mixed_cutoff_or_future_cache_year_is_rejected(self) -> None:
        contexts = [dict(row) for row in self.contexts]
        contexts[0]["as_of_date"] = "2026-10-17"
        with self.assertRaisesRegex(ValueError, "cutoffs_must_match"):
            precompute(contexts, birth_year=2019, as_of_year=2026, scope=self.scope)
        with self.assertRaisesRegex(ValueError, "asof_year_mismatch"):
            precompute(
                self.contexts, birth_year=2019, as_of_year=2027, scope=self.scope
            )

    def test_grid_rejects_user_unknown_time_and_insufficient_history(self) -> None:
        for change in ("user", "unknown", "too_young", "basis"):
            with self.subTest(change=change):
                value = request()
                basis = "standard"
                if change == "user":
                    value["subject_id"] = "user-real-subject"
                elif change == "unknown":
                    value["birth"]["precision"] = "unknown"
                elif change == "too_young":
                    value["birth"]["date"] = "2021-10-18"
                else:
                    basis = "unregistered-school"
                with self.assertRaises(ValueError):
                    synthetic_chart_grid(value, basis=basis)

    def test_grid_does_not_mutate_request_and_frozen_cache_owns_serialized_values(
        self,
    ) -> None:
        self.assertEqual(self.input, self.before)
        fingerprint = self.cache.fingerprint
        changed = deepcopy(self.contexts)
        changed[0]["ziwei_column"]["scored"] = True
        self.assertEqual(self.cache.fingerprint, fingerprint)
        first = json.loads(self.cache.columns_json)[self.contexts[0]["id"]]
        self.assertFalse(first["ziwei_column"]["scored"])
        with self.assertRaises(FrozenInstanceError):
            self.cache.scope = ("other", "synthetic-other", 9)


if __name__ == "__main__":
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(WorkbenchGridNative)
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
