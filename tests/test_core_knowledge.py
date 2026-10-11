"""Source/field/meaning gates: the builtin pack is executable, not four prompts."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

from mingjing_core.knowledge import KnowledgeRegistry
from mingjing_core.knowledge.registry import resolve_pointer


def fixture(system, *, school_id=None, full_pointer=False):
    context = {"owner_user_id": "owner-a", "subject_id": "subject-self", "revision": 7,
               "branch_id": "exact-1", "time_scale": "question" if system == "tarot" else "natal"}
    if system == "bazi":
        data = {"pillars": {name: {"ganzhi": value, "gan": value[0], "zhi": value[1]}
                             for name, value in (("year", "壬辰"), ("month", "甲辰"), ("day", "甲子"), ("hour", "庚午"))},
                "day_master": "甲", "method": {"calendar": "lunar-python", "day_sect": 2}}
        school_id = school_id or "ziping-yueling-v1"
    elif system == "ziwei":
        palace = {"index": 0, "name": "命宫", "ganzhi": "甲子", "major": [{"name": "紫微"}], "minor": [{"name": "左辅"}]}
        palace["linked_palaces"] = [
            {"index": 4, "relation": "三合", "name": "官禄", "ganzhi": "戊辰", "major": [{"name": "天府"}], "minor": []},
            {"index": 8, "relation": "三合", "name": "财帛", "ganzhi": "壬申", "major": [{"name": "武曲", "mutagen": "忌"}], "minor": []},
            {"index": 6, "relation": "对宫", "name": "迁移", "ganzhi": "庚午", "major": [], "minor": [{"name": "右弼"}]}]
        data = {"topic_palace": palace, "method": {"links": "三方四正", "hour_index": 0}}
        school_id = school_id or "sanhe-structure-v1"
    elif system == "astro":
        data = {"aspects": [{"from": "太阳", "to": "月亮", "aspect": "拱相", "angle": 120, "orb": 2.1},
                            {"from": "水星", "to": "土星", "aspect": "刑相", "angle": 90, "orb": 3.2}],
                "aspect_orb": 6, "method": {"zodiac": "tropical", "houses": "Placidus"}}
        school_id = school_id or "tropical-major-aspects-v1"
    elif system == "tarot":
        data = {"cards": [{"position": 1, "card_id": "major-14", "orientation": "upright", "name": "节制"}],
                "spread_id": "focus1", "deck_version": "zhiming-geometric-78-v1", "status": "finalized"}
        school_id = school_id or "zhiming-editorial-v1"
    artifact = {**context, "system": system, "school_id": school_id, "data": data}
    artifacts = {"artifact-1": artifact}
    features = {(system + "." + key if full_pointer else key): {"artifact_id": "artifact-1", "path": ("/data/" if full_pointer else "/") + key, "value": deepcopy(value)} for key, value in data.items()}
    return features, context, artifacts


class CoreKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.registry = KnowledgeRegistry.load_builtin()

    def rule(self, system, *, school_id=None, time_scale=None):
        if system == "tarot" and school_id is None:
            school_id = "zhiming-editorial-v1"
        return self.registry.select(system, time_scale=time_scale or ("question" if system == "tarot" else "natal"), school_id=school_id)[0]

    def declare(self, system, *, school_id=None, full_pointer=False):
        rule = self.rule(system, school_id=school_id)
        args = fixture(system, school_id=school_id, full_pointer=full_pointer)
        return self.registry.declare(rule["rule_id"], *args, rule["allowed_interpretations"][0]["interpretation_id"])

    def test_four_complete_source_rule_field_interpretation_paths(self):
        for system in ("bazi", "ziwei", "astro", "tarot"):
            with self.subTest(system=system):
                result = self.declare(system)
                self.assertTrue(result["eligible"], result)
                claim = result["claim"]
                self.assertEqual(claim["real_world_link_status"], "not_established")
                self.assertTrue(claim["feature_refs"])
                self.assertTrue(claim["source_refs"])
                self.assertTrue(claim["limitations"])
                self.assertTrue(claim["counter_factors"])
                self.assertNotEqual(claim["editorial_status"], "expert_reviewed")
                sources = self.registry.sources(claim["rule_id"])
                self.assertEqual(len(sources), len(claim["source_refs"]))
                self.assertTrue(all(source["scope_note"] and source["locator"] for source in sources))

    def test_actual_chart_feature_key_and_data_root_contract(self):
        for system in ("bazi", "ziwei", "astro", "tarot"):
            result = self.declare(system, full_pointer=True)
            self.assertTrue(result["eligible"], result)
            self.assertTrue(all(ref["path"].startswith("/data/") for ref in result["feature_refs"]))

    def test_no_mandatory_cross_system_or_cross_time_scope(self):
        self.assertEqual({r["system"] for r in self.registry.select("bazi")}, {"bazi"})
        self.assertEqual(self.registry.select("bazi", time_scale="daily"), [])
        self.assertEqual(self.registry.select("ziwei", school_id="unknown-school"), [])
        self.assertEqual(self.registry.select("astro", topic="drug_dosage"), [])
        self.assertEqual(self.registry.select("unknown"), [])

    def test_unknown_rule_is_explicit_gap_and_no_claim(self):
        result = self.registry.declare("made-up", {}, {}, {}, "success")
        self.assertEqual(result["status"], "RULE_GAP")
        self.assertNotIn("claim", result)

    def test_well_formed_reference_does_not_support_arbitrary_life_claim(self):
        features, context, artifacts = fixture("bazi")
        rule = self.rule("bazi")
        self.assertTrue(self.registry.evaluate(rule["rule_id"], features, context, artifacts)["eligible"])
        result = self.registry.declare(rule["rule_id"], features, context, artifacts, "必发财")
        self.assertEqual(result["status"], "UNSUPPORTED_INFERENCE")
        self.assertNotIn("claim", result)

    def test_owner_subject_revision_branch_and_time_gates(self):
        for field, value, error in (("owner_user_id", "other-owner", "AUTH_SCOPE_ERROR"),
                                    ("subject_id", "friend", "AUTH_SCOPE_ERROR"),
                                    ("revision", 6, "STALE_INPUT"),
                                    ("revision", True, "STALE_INPUT"),
                                    ("branch_id", "noon-guessed", "SCOPE_MISMATCH"),
                                    ("time_scale", "yearly", "SCOPE_MISMATCH")):
            with self.subTest(field=field, value=value):
                features, context, artifacts = fixture("bazi")
                artifacts["artifact-1"][field] = value
                result = self.registry.evaluate(self.rule("bazi")["rule_id"], features, context, artifacts)
                self.assertEqual(result["status"], error)
                self.assertNotIn("claim", result)

    def test_missing_context_never_borrows_artifact_identity(self):
        features, context, artifacts = fixture("bazi")
        del context["owner_user_id"]
        self.assertEqual(self.registry.evaluate(self.rule("bazi")["rule_id"], features, context, artifacts)["status"], "AUTH_SCOPE_ERROR")

    def test_changed_reference_and_relabelled_semantic_path_rejected(self):
        features, context, artifacts = fixture("bazi")
        features["day_master"]["value"] = "乙"
        self.assertEqual(self.registry.evaluate(self.rule("bazi")["rule_id"], features, context, artifacts)["status"], "REFERENCE_ERROR")
        features, context, artifacts = fixture("bazi")
        artifacts["artifact-1"]["data"]["fake"] = "甲"
        features["day_master"]["path"] = "/fake"
        self.assertEqual(self.registry.evaluate(self.rule("bazi")["rule_id"], features, context, artifacts)["status"], "REFERENCE_ERROR")

    def test_bazi_premises_negative_missing_hour_and_wrong_day_master(self):
        for mutation, expected in ((lambda data: data["pillars"].pop("hour"), "RULE_GAP"),
                                   (lambda data: data.update(day_master="乙"), "REFERENCE_ERROR")):
            features, context, artifacts = fixture("bazi")
            mutation(artifacts["artifact-1"]["data"])
            for key in features:
                features[key]["value"] = deepcopy(artifacts["artifact-1"]["data"][key])
            self.assertEqual(self.registry.evaluate(self.rule("bazi")["rule_id"], features, context, artifacts)["status"], expected)

    def test_ziwei_full_link_structure_not_single_star_and_preserves_counterfactor(self):
        result = self.declare("ziwei")
        for word in ("紫微", "天府", "武曲", "右弼", "命宫", "官禄", "财帛", "迁移", "忌"):
            self.assertIn(word, result["claim"]["text"])
        self.assertTrue(any("化忌" in factor for factor in result["claim"]["counter_factors"]))
        for links, expected in (([], "RULE_GAP"), ([4, 8, 5], "REFERENCE_ERROR")):
            features, context, artifacts = fixture("ziwei")
            palace = artifacts["artifact-1"]["data"]["topic_palace"]
            if not links:
                palace["linked_palaces"] = []
            else:
                for linked, index in zip(palace["linked_palaces"], links):
                    linked["index"] = index
            features["topic_palace"]["value"] = deepcopy(palace)
            self.assertEqual(self.registry.evaluate(self.rule("ziwei")["rule_id"], features, context, artifacts)["status"], expected)

    def test_astro_geometry_and_orb_negative_and_conflict_preserved(self):
        result = self.declare("astro")
        self.assertTrue(any("协调与张力" in factor for factor in result["claim"]["counter_factors"]))
        for field, value, expected in (("angle", 90, "RULE_GAP"), ("orb", 8, "REFERENCE_ERROR"), ("orb", float("nan"), "REFERENCE_ERROR")):
            features, context, artifacts = fixture("astro")
            artifacts["artifact-1"]["data"]["aspects"][0][field] = value
            features["aspects"]["value"] = deepcopy(artifacts["artifact-1"]["data"]["aspects"])
            self.assertEqual(self.registry.evaluate(self.rule("astro")["rule_id"], features, context, artifacts)["status"], expected)

    def test_tarot_original_editorial_and_waite_original_distinct(self):
        editorial = self.declare("tarot")
        waite = self.declare("tarot", school_id="rws-waite-primary-v1")
        self.assertTrue(waite["eligible"], waite)
        self.assertNotEqual(editorial["claim"]["source_refs"], waite["claim"]["source_refs"])
        self.assertEqual(editorial["claim"]["claim_type"], "symbolic_reflection")
        self.assertEqual(waite["claim"]["claim_type"], "traditional_interpretation")
        features, context, artifacts = fixture("tarot", school_id="rws-waite-primary-v1")
        artifacts["artifact-1"]["data"]["cards"][0]["orientation"] = "reversed"
        features["cards"]["value"] = deepcopy(artifacts["artifact-1"]["data"]["cards"])
        self.assertEqual(self.registry.evaluate(self.rule("tarot", school_id="rws-waite-primary-v1")["rule_id"], features, context, artifacts)["status"], "RULE_GAP")

    def test_complete_78_card_deck_and_each_orientation_is_real_editorial_text(self):
        catalog = json.loads(Path("mingjing_core/knowledge/tarot_meanings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(catalog["cards"]), 78)
        self.assertEqual(sum(card["group"] == "major" for card in catalog["cards"]), 22)
        self.assertEqual(sum(card["group"] == "minor" for card in catalog["cards"]), 56)
        self.assertEqual(len({card["upright"] for card in catalog["cards"]}), 78)
        for card in catalog["cards"]:
            for orientation in ("upright", "reversed"):
                features, context, artifacts = fixture("tarot")
                artifacts["artifact-1"]["data"]["cards"] = [{"position": 1, "card_id": card["card_id"], "orientation": orientation, "name": card["name"]}]
                features["cards"]["value"] = deepcopy(artifacts["artifact-1"]["data"]["cards"])
                rule = self.rule("tarot")
                result = self.registry.declare(rule["rule_id"], features, context, artifacts, "card_reflection")
                self.assertTrue(result["eligible"], result)
                self.assertIn(card[orientation], result["claim"]["text"])
                self.assertIn(card["misreading"], result["claim"]["counter_factors"])

    def test_draw_status_count_identity_position_and_version_negative(self):
        changes = (("status", "awaiting_selection", "DRAW_MISMATCH"),
                   ("spread_id", "choice5", "DRAW_MISMATCH"),
                   ("deck_version", "other-deck", "RULE_GAP"))
        for key, value, expected in changes:
            features, context, artifacts = fixture("tarot")
            artifacts["artifact-1"]["data"][key] = value
            features[key]["value"] = deepcopy(value)
            self.assertEqual(self.registry.evaluate(self.rule("tarot")["rule_id"], features, context, artifacts)["status"], expected)
        for key, value in (("position", 2), ("name", "太阳"), ("card_id", "fake-card")):
            features, context, artifacts = fixture("tarot")
            artifacts["artifact-1"]["data"]["cards"][0][key] = value
            features["cards"]["value"] = deepcopy(artifacts["artifact-1"]["data"]["cards"])
            self.assertEqual(self.registry.evaluate(self.rule("tarot")["rule_id"], features, context, artifacts)["status"], "DRAW_MISMATCH")

    def test_declaration_is_deterministic_not_model_id_or_personal_fact(self):
        first, second = self.declare("bazi"), self.declare("bazi")
        self.assertEqual(first["claim"], second["claim"])
        features, context, artifacts = fixture("bazi")
        context["revision"] += 1
        artifacts["artifact-1"]["revision"] = context["revision"]
        rule = self.rule("bazi")
        revised = self.registry.declare(rule["rule_id"], features, context, artifacts, "seasonal_framework")
        self.assertNotEqual(first["claim"]["claim_id"], revised["claim"]["claim_id"])

    def test_json_pointer_escape_type_and_negative_index(self):
        self.assertEqual(resolve_pointer({"a/b": {"~": [7]}}, "/a~1b/~0/0"), 7)
        for pointer in ("", "/x/-1", "/x/01", "/x/1", "/a~2b"):
            with self.assertRaises(ValueError):
                resolve_pointer({"x": [7]}, pointer)

    def test_builtin_objects_are_not_mutated_by_model_payloads(self):
        rule = self.rule("bazi")
        rule["allowed_interpretations"][0]["text_template"] = "必发财"
        self.assertNotIn("必发财", self.declare("bazi")["claim"]["text"])
        bad = self.registry.get("bazi.natal.seasonal-structure.v1")
        bad["predicate_id"] = "shell.exec"
        with self.assertRaises(ValueError):
            KnowledgeRegistry([bad], self.registry.sources())
        bad["predicate_id"] = "bazi_structure"
        bad["editorial_status"] = "expert_reviewed"
        with self.assertRaises(ValueError):
            KnowledgeRegistry([bad], self.registry.sources())

    def test_declared_claim_cannot_be_reworded_into_prediction(self):
        features, context, artifacts = fixture("bazi")
        result = self.declare("bazi")
        self.assertTrue(self.registry.validate_claim(result["claim"], features, context, artifacts)["eligible"])
        result["claim"]["text"] = "此盘保证你明年发财。"
        invalid = self.registry.validate_claim(result["claim"], features, context, artifacts)
        self.assertEqual(invalid["status"], "UNSUPPORTED_INFERENCE")
        self.assertNotIn("claim", invalid)

    def test_composite_artifact_requires_every_feature_explicit_natal_scope(self):
        features, context, artifacts = fixture("bazi", full_pointer=True)
        artifacts["artifact-1"]["time_scale"] = "natal_with_explicit_separate_target_layers"
        rule = self.rule("bazi")
        self.assertEqual(self.registry.evaluate(rule["rule_id"], features, context, artifacts)["status"], "SCOPE_MISMATCH")
        for feature in features.values():
            feature["time_scale"] = "natal"
        self.assertTrue(self.registry.evaluate(rule["rule_id"], features, context, artifacts)["eligible"])
        features["bazi.method"]["time_scale"] = "daily"
        self.assertEqual(self.registry.evaluate(rule["rule_id"], features, context, artifacts)["status"], "SCOPE_MISMATCH")

    @unittest.skipUnless(importlib.util.find_spec("lunar_python"), "requires actual lunar-python")
    def test_actual_chart_adapter_to_released_rule_and_declaration(self):
        from mingjing_core.adapters.charts import ChartAdapter
        archive = {"owner_user_id": "owner-a", "subject_id": "self", "user": {"gender": "男", "birth": {
            "solar_datetime": "2012-05-03 13:18", "timezone_offset": 8, "time_precision": "exact",
            "location": {"lng": 104.07, "lat": 30.67}}}}
        result = ChartAdapter("owner-a").calculate(archive, "2026-10-11", ["bazi"], 7, "self")
        self.assertEqual(result["errors"], [])
        features = {feature["feature_key"]: feature for feature in result["features"].values()}
        artifacts = {identifier: dict(artifact, school_id=result["profiles"][artifact["profile_id"]]["school_id"])
                     for identifier, artifact in result["artifacts"].items()}
        context = {"owner_user_id": "owner-a", "subject_id": "self", "revision": 7,
                   "branch_id": result["branches"][0]["id"], "time_scale": "natal"}
        claim = self.registry.declare("bazi.natal.seasonal-structure.v1", features, context, artifacts, "seasonal_framework")
        self.assertTrue(claim["eligible"], claim)
        self.assertIn("甲辰", claim["claim"]["text"])
        self.assertNotIn("xiyongshen", {ref["feature_key"] for ref in claim["claim"]["feature_refs"]})


if __name__ == "__main__":
    unittest.main()
