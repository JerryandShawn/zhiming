"""Retained strict-side/declared-range invariants after old U9 withdrawal."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from mingjing_core.adapters.charts.jie_uncertainty import boundaries_in_range, probe
from mingjing_core.adapters.charts.worker import load_engine


class JieGeometry(unittest.TestCase):
    def test_all_twelve_jie_strict_sides_remain_inside_a_declared_range(self) -> None:
        engine = load_engine("bazi")
        table = engine.Solar.fromYmdHms(2026, 7, 1, 12, 0, 0).getLunar().getJieQiTable()
        for name in (
            "立春",
            "惊蛰",
            "清明",
            "立夏",
            "芒种",
            "小暑",
            "立秋",
            "白露",
            "寒露",
            "立冬",
            "大雪",
            "XIAO_HAN",
        ):
            boundary = datetime.fromisoformat(table[name].toYmdHms())
            left = boundary.replace(second=0, microsecond=0) - timedelta(minutes=1)
            right = left + timedelta(minutes=3)
            rows = boundaries_in_range(engine, left.isoformat(), right.isoformat(), 8)
            self.assertEqual(len(rows), 1)
            before, after = (
                datetime.fromisoformat(value) for value in rows[0]["samples"]
            )
            self.assertLess(before, boundary)
            self.assertGreater(after, boundary)
            self.assertTrue(left <= before < after <= right)

    def test_minute_sampling_is_clipped_rather_than_widening_the_declared_range(
        self,
    ) -> None:
        engine = load_engine("bazi")
        boundary = datetime.fromisoformat("2026-02-04T04:02:08")
        left = boundary.replace(second=0)
        right = left + timedelta(minutes=1)
        rows = boundaries_in_range(engine, left.isoformat(), right.isoformat(), 8)
        self.assertEqual(rows[0]["samples"], ["2026-02-04 04:02", "2026-02-04 04:03"])
        self.assertEqual(
            boundaries_in_range(engine, left.isoformat(), left.isoformat(), 8), []
        )

    def test_two_minute_probe_is_diagnostic_and_not_a_birth_fact(self) -> None:
        engine = load_engine("bazi")
        result = probe(engine, "2026-02-04 04:02", 8)
        self.assertEqual(result["calendar_boundary"], "2026-02-04T04:02:08+08:00")
        self.assertEqual(result["distance_seconds"], 8)
        self.assertIsNone(probe(engine, "2026-02-04 04:05", 8))


if __name__ == "__main__":
    unittest.main()
