import copy
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mingjing_core.adapters.charts import ChartAdapter


def archive():
    return {"owner_user_id": "owner-a", "subject_id": "self", "user": {"gender": "男", "birth": {
        "solar_datetime": "2012-05-03 13:18", "timezone_offset": 8,
        "time_precision": "exact", "location": {"lng": 104.07, "lat": 30.67}}}}


def fake_bazi(args):
    rows = {name: {"ganzhi": ganzhi, "gan": ganzhi[0], "zhi": ganzhi[1],
                  "shishen_gan": "比肩", "shishen_zhi": "正印"}
            for name, ganzhi in zip(("year", "month", "day", "hour"), ("壬辰", "甲辰", "甲子", "庚午"))}
    return {"pillars": rows, "day_master": "甲", "method": {"day_sect": 2}, "xiyongshen": ["火"],
            "day": {"date": args["date"], "sample_at": args["date"] + " 12:00:00"},
            "dayun": [{"ganzhi": "乙巳", "start_age": 1}]}


def fake_ziwei(args):
    palaces = [{"index": index, "name": "命宫" if index == 0 else "宫" + str(index),
                "ganzhi": "甲子", "major": [{"name": "紫微"}], "minor": [{"name": "左辅"}]}
               for index in range(12)]
    for p in palaces:
        p["linked_palaces"] = [{**{key: palaces[index][key] for key in ("index", "name", "ganzhi", "major", "minor")},
                                 "relation": relation} for index, relation in
                                (((p["index"] + 4) % 12, "三合"), ((p["index"] + 8) % 12, "三合"),
                                 ((p["index"] + 6) % 12, "对宫"))]
    return {"palaces": palaces, "method": {"hour_index": int(args["datetime"][11:13]) // 2},
            "horoscope": {level: {"palace_names": [p["name"] for p in palaces], "mutagen_links": []}
                          for level in ("decadal", "yearly", "monthly", "daily")}}


def fake_astro(args):
    return {"method": {"houses": "Placidus", "ephemeris": "Moshier"},
            "planets": {"太阳": {"longitude": 11}, "月亮": {"longitude": 102}},
            "aspects": [{"from": "太阳", "to": "月亮", "aspect": "刑相", "angle": 90, "orb": 1}],
            "aspect_orb": 6, "houses": [{"house": 1, "longitude": 0}],
            "transits": {"sample_time": args["date"] + "T12:00:00", "timezone_offset": 8}}


class ChartContractTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def runner(system, args):
            self.calls.append((system, copy.deepcopy(args)))
            return {"bazi": fake_bazi, "ziwei": fake_ziwei, "astro": fake_astro}[system](args)
        self.adapter = ChartAdapter("owner-a", runner=runner)

    def run_chart(self, arc=None, systems=("bazi", "ziwei", "astro")):
        return self.adapter.calculate(arc or archive(), "2026-10-11", systems, 7, "self")

    def test_only_requested_capability_and_exact_refs(self):
        result = self.run_chart(systems=["bazi"])
        self.assertEqual(result["errors"], [])
        self.assertEqual([call[0] for call in self.calls], ["bazi"])
        for feature in result["features"].values():
            artifact = result["artifacts"][feature["artifact_id"]]
            actual = artifact
            for segment in feature["path"].lstrip("/").split("/"):
                actual = actual[segment]
            self.assertEqual(feature["value"], actual)
            self.assertEqual(feature["owner_user_id"], "owner-a")
            self.assertEqual(feature["subject_id"], "self")
            self.assertEqual(feature["revision"], 7)
            self.assertEqual(feature["stability"], "exact_input")

    def test_owner_scope_before_any_calculation(self):
        arc = archive(); arc["owner_user_id"] = "owner-b"
        result = self.run_chart(arc)
        self.assertEqual(result["errors"][0]["code"], "AUTH_SCOPE_ERROR")
        self.assertEqual(self.calls, [])
        result = self.adapter.calculate(archive(), "2026-10-11", ["bazi"], 7,
                                        {"id": "self", "owner_user_id": "owner-b"})
        self.assertEqual(result["errors"][0]["code"], "AUTH_SCOPE_ERROR")

    def test_subject_scope_before_any_calculation(self):
        arc = archive(); arc["subject_id"] = "friend-1"
        self.assertEqual(self.run_chart(arc)["errors"][0]["code"], "AUTH_SCOPE_ERROR")
        self.assertEqual(self.calls, [])

    def test_missing_offset_does_not_assume_utc8(self):
        arc = archive(); del arc["user"]["birth"]["timezone_offset"]
        result = self.run_chart(arc)
        self.assertEqual(len(result["errors"]), 3)
        self.assertTrue(all(error["code"] == "MISSING_INPUT" for error in result["errors"]))
        self.assertEqual(self.calls, [])

    def test_missing_gender_is_not_assumed_male(self):
        arc = archive(); del arc["user"]["gender"]
        result = self.run_chart(arc)
        self.assertEqual([call[0] for call in self.calls], ["astro"])
        self.assertEqual({error["system"] for error in result["errors"]}, {"bazi", "ziwei"})

    def test_unknown_does_not_confirm_noon_or_mutate_original(self):
        arc = archive(); birth = arc["user"]["birth"]
        birth.update(time_precision="unknown", time_unknown=True, solar_date="2012-05-03")
        del birth["solar_datetime"]
        original = copy.deepcopy(arc)
        result = self.run_chart(arc, ["bazi"])
        self.assertEqual(arc, original)
        self.assertEqual(len(result["branches"]), 5)
        self.assertTrue(all(branch["coverage"] == "sampled_not_continuous" for branch in result["branches"]))
        self.assertTrue(all(not branch["confirmed_birth_time"] for branch in result["branches"]))
        self.assertTrue(all("solar_datetime" not in profile["input"]["declared_birth"]
                            for profile in result["profiles"].values()))
        self.assertTrue(all(feature["stability"] == "sampled_stable" for feature in result["features"].values()))

    def test_interval_is_sampling_not_a_continuous_proof(self):
        arc = archive(); arc["user"]["birth"].update(time_precision="interval",
            time_interval={"start": "2012-05-03 12:00", "end": "2012-05-03 14:00"})
        result = self.run_chart(arc, ["ziwei"])
        self.assertEqual(len(result["branches"]), 5)
        methods = [feature for feature in result["features"].values() if feature["feature_key"] == "ziwei.method"]
        self.assertTrue(all(feature["stability"] == "conditional" for feature in methods))
        self.assertTrue(all(branch["sampling_range"]["inclusive"] for branch in result["branches"]))

    def test_approximate_has_three_explicit_branches(self):
        arc = archive(); arc["user"]["birth"].update(time_precision="approximate", time_uncertainty_minutes=30)
        result = self.run_chart(arc, ["bazi"])
        self.assertEqual([branch["civil_datetime"] for branch in result["branches"]],
                         ["2012-05-03 12:48", "2012-05-03 13:18", "2012-05-03 13:48"])

    def test_invalid_precision_and_seconds_are_not_silently_truncated(self):
        for changes in ({"time_precision": "rough"}, {"solar_datetime": "2012-05-03 13:18:20"},
                        {"solar_datetime": "2012-05-03"},
                        {"time_precision": "approximate", "time_uncertainty_minutes": 1.5}):
            arc = archive(); arc["user"]["birth"].update(changes)
            self.assertEqual(self.run_chart(arc)["errors"][0]["code"], "MISSING_INPUT")
        self.assertEqual(self.calls, [])

    def test_one_failed_sample_prevents_sample_stability_claim(self):
        arc = archive(); arc["user"]["birth"].update(time_precision="approximate", time_uncertainty_minutes=30)
        def runner(system, args):
            if args["datetime"].endswith("12:48"):
                raise RuntimeError("fixture failure")
            return fake_bazi(args)
        result = ChartAdapter("owner-a", runner=runner).calculate(arc, "2026-10-11", ["bazi"], 7, "self")
        self.assertEqual(result["errors"][0]["code"], "CALCULATION_ERROR")
        self.assertTrue(all(feature["stability"] == "conditional" for feature in result["features"].values()))

    def test_bazi_heuristic_is_not_a_feature_or_full_strength_analysis(self):
        result = self.run_chart(systems=["bazi"])
        artifact = next(iter(result["artifacts"].values()))
        self.assertNotIn("xiyongshen", artifact["data"])
        self.assertEqual(artifact["data"]["legacy_heuristic_not_for_interpretation"], ["火"])
        self.assertFalse(any("xiyongshen" in key for key in result["features"]))
        self.assertIn("完整旺衰", artifact["data"]["relations"]["not_implemented"])
        self.assertEqual(artifact["data"]["month_command"]["branch"], "辰")

    def test_ziwei_links_are_real_and_not_a_keyword_summary(self):
        result = self.run_chart(systems=["ziwei"])
        feature = next(feature for feature in result["features"].values() if feature["feature_key"] == "ziwei.topic_palace")
        self.assertEqual([link["index"] for link in feature["value"]["linked_palaces"]], [4, 8, 6])
        artifact = result["artifacts"][feature["artifact_id"]]
        self.assertEqual(len(artifact["data"]["palaces"]), 12)
        self.assertEqual(feature["value"]["linked_palaces"][0]["major"], artifact["data"]["palaces"][4]["major"])

    def test_forged_ziwei_link_is_a_calculation_error(self):
        def runner(system, args):
            data = fake_ziwei(args); data["palaces"][0]["linked_palaces"][0]["index"] = 3
            return data
        result = ChartAdapter("owner-a", runner=runner).calculate(archive(), "2026-10-11", ["ziwei"], 7, "self")
        self.assertEqual(result["artifacts"], {})
        self.assertEqual(result["errors"][0]["code"], "CALCULATION_ERROR")

    def test_aspects_value_and_orb_are_validated_before_publication(self):
        result = self.run_chart(systems=["astro"])
        self.assertEqual(result["errors"], [])
        def runner(system, args):
            data = fake_astro(args); data["aspects"][0]["orb"] = 0
            return data
        forged = ChartAdapter("owner-a", runner=runner).calculate(archive(), "2026-10-11", ["astro"], 7, "self")
        self.assertEqual(forged["artifacts"], {})
        self.assertIn("真实天体位置", forged["errors"][0]["reason"])

    def test_revision_changes_artifact_profile_and_feature_identity(self):
        first = self.run_chart(systems=["bazi"])
        second = self.adapter.calculate(archive(), "2026-10-11", ["bazi"], 8, "self")
        self.assertFalse(set(first["artifacts"]) & set(second["artifacts"]))
        self.assertFalse(set(first["features"]) & set(second["features"]))
        same = self.run_chart(systems=["bazi"])
        self.assertEqual(first, same)


CHART_PYTHON = os.environ.get("CHART_PYTHON", sys.executable)


def has_dependency(module):
    process = subprocess.run([CHART_PYTHON, "-c", "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)", module],
                             capture_output=True, encoding="utf-8", timeout=10)
    return process.returncode == 0


class ActualChartTests(unittest.TestCase):
    def calculate(self, arc, systems, date="2026-10-11"):
        return ChartAdapter("owner-a", python=CHART_PYTHON).calculate(arc, date, systems, 7, "self")

    @unittest.skipUnless(has_dependency("lunar_python"), "chart interpreter lacks lunar_python")
    def test_actual_bazi_known_vector_and_target_month_intervals(self):
        result = self.calculate(archive(), ["bazi"])
        self.assertEqual(result["errors"], [])
        artifact = next(iter(result["artifacts"].values()))
        self.assertEqual([artifact["data"]["pillars"][name]["ganzhi"] for name in ("year", "month", "day", "hour")],
                         ["壬辰", "甲辰", "甲子", "庚午"])
        self.assertEqual(artifact["data"]["day"]["sample_at"], "2026-10-11 12:00:00")
        for month in artifact["data"]["target_liuyue"]:
            self.assertLessEqual(datetime.fromisoformat(month["period_start"]), datetime.fromisoformat(month["sample_at"]))
            self.assertLess(datetime.fromisoformat(month["sample_at"]), datetime.fromisoformat(month["period_end_exclusive"]))
        profile = next(iter(result["profiles"].values()))
        self.assertEqual(profile["actual_method"]["day_sect"], 2)
        self.assertFalse(profile["actual_method"]["equation_of_time_applied"])
        self.assertIn("lunar-python", profile["versions"])

    @unittest.skipUnless(has_dependency("lunar_python"), "chart interpreter lacks lunar_python")
    def test_same_actual_instant_with_two_civil_offsets_has_same_bazi(self):
        first = archive(); first["user"]["birth"]["solar_datetime"] = "2024-02-04 16:20"
        second = copy.deepcopy(first)
        second["user"]["birth"].update(solar_datetime="2024-02-04 08:20", timezone_offset=0)
        a, b = self.calculate(first, ["bazi"]), self.calculate(second, ["bazi"])
        self.assertEqual(a["errors"], []); self.assertEqual(b["errors"], [])
        self.assertEqual(next(iter(a["artifacts"].values()))["data"]["pillars"],
                         next(iter(b["artifacts"].values()))["data"]["pillars"])

    @unittest.skipUnless(has_dependency("lunar_python"), "chart interpreter lacks lunar_python")
    def test_exact_jie_boundary_changes_month_not_calendar_date(self):
        first = archive(); first["user"]["birth"].update(solar_datetime="2024-02-04 16:20", location={"lng": 120, "lat": 30})
        second = copy.deepcopy(first); second["user"]["birth"]["solar_datetime"] = "2024-02-04 16:30"
        a, b = self.calculate(first, ["bazi"]), self.calculate(second, ["bazi"])
        self.assertEqual(a["errors"], []); self.assertEqual(b["errors"], [])
        pa, pb = [next(iter(result["artifacts"].values()))["data"]["pillars"] for result in (a, b)]
        self.assertNotEqual(pa["month"]["ganzhi"], pb["month"]["ganzhi"])
        self.assertNotEqual(pa["year"]["ganzhi"], pb["year"]["ganzhi"])

    @unittest.skipUnless(has_dependency("lunar_python"), "chart interpreter lacks lunar_python")
    def test_zi_hour_sect_two_keeps_day_until_midnight(self):
        arc = archive(); arc["user"]["birth"].update(location={"lng": 120, "lat": 30})
        values = []
        for time in ("2012-05-03 22:59", "2012-05-03 23:00", "2012-05-04 00:00"):
            arc["user"]["birth"]["solar_datetime"] = time
            result = self.calculate(arc, ["bazi"])
            self.assertEqual(result["errors"], [])
            values.append(next(iter(result["artifacts"].values()))["data"]["pillars"])
        self.assertEqual(values[0]["day"], values[1]["day"])
        self.assertNotEqual(values[1]["day"], values[2]["day"])

    @unittest.skipUnless(has_dependency("py_iztro"), "chart interpreter lacks py_iztro")
    def test_actual_ziwei_complete_links_and_distinct_temporal_layers(self):
        result = self.calculate(archive(), ["ziwei"])
        self.assertEqual(result["errors"], [])
        data = next(iter(result["artifacts"].values()))["data"]
        self.assertEqual(len(data["palaces"]), 12)
        self.assertEqual(len(data["topic_palace"]["linked_palaces"]), 3)
        self.assertEqual(data["horoscope"]["target_date"], "2026-10-11")
        self.assertTrue(all("mutagen_links" in data["horoscope"][level] for level in ("decadal", "yearly", "monthly", "daily")))
        profile = next(iter(result["profiles"].values()))
        self.assertIn("by_solar_defaults", profile["actual_method"])
        self.assertEqual(profile["versions"]["py-iztro"], "0.1.5")

    @unittest.skipUnless(has_dependency("swisseph"), "chart interpreter lacks swisseph")
    def test_actual_astro_utc_flags_and_snapshot_not_solar_time(self):
        result = self.calculate(archive(), ["astro"])
        self.assertEqual(result["errors"], [])
        data = next(iter(result["artifacts"].values()))["data"]
        self.assertEqual(data["utc_time"], "2012-05-03T05:18:00Z")
        self.assertEqual(len(data["calculation_flags"]["natal"]), 10)
        self.assertEqual(len(data["calculation_flags"]["transit_snapshot"]), 10)
        profile = next(iter(result["profiles"].values()))
        self.assertEqual(profile["actual_method"]["ephemeris"], ["Moshier"])
        self.assertEqual(profile["fallback"], [])
        self.assertEqual(data["transits"]["sample_time"], "2026-10-11T12:00:00")

    @unittest.skipUnless(has_dependency("swisseph"), "chart interpreter lacks swisseph")
    def test_high_latitude_failure_does_not_silently_change_placidus(self):
        arc = archive(); arc["user"]["birth"]["location"]["lat"] = 89
        result = self.calculate(arc, ["astro"])
        self.assertEqual(result["artifacts"], {})
        self.assertEqual(result["errors"][0]["code"], "CALCULATION_ERROR")
        self.assertEqual(result["errors"][0]["requested_method"]["houses"], "Placidus")
        self.assertEqual(result["errors"][0]["fallback"], [])


if __name__ == "__main__":
    unittest.main()
