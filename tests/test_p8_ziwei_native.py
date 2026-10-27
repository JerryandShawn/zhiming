"""Charts-only engine comparison using the official public API example date."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.worker import load_engine  # noqa: E402
from mingjing_core.adapters.charts.ziwei_flying import palace_flying_transformations  # noqa: E402
from mingjing_core.adapters.charts.ziwei_flying_support import flying_profile  # noqa: E402


def chart(value: str, target: str = "2026-10-18"):
    engine = load_engine("ziwei")
    astro, corrected = engine.build(datetime.fromisoformat(value), 0, "女", 0)
    data = engine.natal(astro, corrected)
    h = astro.horoscope(target)
    data["horoscope"] = {
        "target_date": target,
        **{name: engine.scope(getattr(h, name)) for name in ("decadal", "yearly", "monthly", "daily")},
    }
    return astro, data


class NativeFlying(unittest.TestCase):
    def test_public_example_all_48_links_match_installed_js_functions(self) -> None:
        astro, data = chart("2000-08-16T03:00:00")
        result = palace_flying_transformations(data)
        self.assertTrue(result["complete"])
        for edge in result["edges"]:
            source, label = edge["source"]["palace_index"], edge["mutagen"]
            target = edge["locations"][0]["palace_index"]
            js = astro._js_astro_obj.palace(source)
            self.assertTrue(js.fliesTo(target, label))
            self.assertEqual(bool(js.selfMutaged(label)), edge["self_transformation"])
            self.assertEqual(int(js.mutagedPlaces()["禄权科忌".index(label)].index), target)
            # A different geometric target must not become a second true fly.
            self.assertFalse(js.fliesTo((target + 1) % 12, label))

    def test_40_table_cells_and_four_time_layers_against_actual_engine(self) -> None:
        profile = flying_profile()
        seen = set()
        for value in ("2000-08-16T03:00:00", "1995-03-10T09:00:00"):
            astro, data = chart(value)
            result = palace_flying_transformations(data)
            self.assertTrue(result["natal"]["complete"])
            for edge in result["edges"]:
                source = edge["source"]["palace_index"]
                seen.add(edge["source"]["ganzhi"][0])
                destination = astro._js_astro_obj.palace(source).mutagedPlaces()[
                    profile["labels"].index(edge["mutagen"])
                ]
                self.assertEqual(int(destination.index), edge["locations"][0]["palace_index"])
            for layer in result["temporal_layers"].values():
                self.assertEqual(layer["status"], "resolved")
                self.assertTrue(layer["matches_named_table"])
        self.assertEqual(seen, set(profile["table"]))

    def test_fixed_public_example_geometry_snapshot(self) -> None:
        _, data = chart("2000-08-16T03:00:00")
        result = palace_flying_transformations(data)
        self.assertEqual(data["palaces"][0]["ganzhi"], "戊寅")
        self.assertEqual(data["palaces"][0]["name"], "财帛")
        self.assertEqual([edge["locations"][0]["palace_index"] for edge in result["edges"][:4]], [10, 9, 2, 3])
        self.assertEqual([edge["star"] for edge in result["edges"][:4]], ["贪狼", "太阴", "右弼", "天机"])
        self.assertEqual(result["temporal_layers"]["yearly"]["ganzhi"], "丙午")
        self.assertEqual(result["temporal_layers"]["yearly"]["life_palace"]["palace_index"], 4)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeFlying)
    result = unittest.TextTestRunner(stream=sys.stderr).run(suite)
    print(json.dumps({"tests": result.testsRun, "successful": result.wasSuccessful(), "skipped": len(result.skipped)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
