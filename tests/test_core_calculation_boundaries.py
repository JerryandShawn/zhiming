"""Synthetic fixtures only; real isolated calculators and honest rule boundaries."""
from copy import deepcopy
from datetime import datetime
import importlib.util
import json
import math
import sys
import unittest

from mingjing_core.adapters.charts import ChartAdapter, ChartsAdapter
from mingjing_core.domain.calculation import CalculationFeature
from mingjing_core.knowledge import KnowledgeRegistry
from hermes.tarot_deck import card, SPREADS, DECK_VERSION, MEANING_VERSION, METHOD_VERSION
from tests.test_core_charts import archive, fake_bazi, fake_astro, fake_ziwei, CHART_PYTHON, has_dependency


def ready_draw():
    return {"id": "synthetic-draw", "subject_id": "self", "revision": 2,
            "status": "ready", "spread_id": "focus1", "spread": deepcopy(SPREADS["focus1"]),
            "deck_version": DECK_VERSION, "meaning_version": MEANING_VERSION,
            "method_version": METHOD_VERSION, "context_snapshot": {}, "context_revoked": False,
            "cards": [{"position": 1, "label": SPREADS["focus1"]["positions"][0], "back_id": "opaque",
                       "revealed": True, "card_id": "major-14", "orientation": "upright", "card": card("major-14")}]}


class CalculationBoundaryContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = KnowledgeRegistry.load_builtin()
        self.adapter = ChartsAdapter("owner-a", runner=lambda s, a: {"bazi": fake_bazi, "astro": fake_astro, "ziwei": fake_ziwei}[s](a))

    def test_public_alias_and_run(self):
        self.assertIs(ChartsAdapter, ChartAdapter)
        self.assertEqual(self.adapter.run(archive(), "2026-10-11", ["bazi"], 7, "self")["errors"], [])

    def test_missing_gender_blocks_only_gender_dependent_engines(self):
        a = archive(); del a["user"]["gender"]
        result = self.adapter.run(a, "2026-10-11", ["bazi", "ziwei", "astro"], 7, "self")
        self.assertEqual({x["system"] for x in result["errors"]}, {"bazi", "ziwei"})
        self.assertEqual({a["system"] for a in result["artifacts"].values()}, {"astro"})

    def test_nested_nan_and_infinity_fail_closed(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=str(value)):
                a = archive(); a["user"]["birth"]["unrelated_metadata"] = {"nested": [value]}
                result = self.adapter.run(a, "2026-10-11", ["bazi"], 7, "self")
                self.assertFalse(result["artifacts"])
                bad = ChartsAdapter("owner-a", runner=lambda s, a: {**fake_bazi(a), "nested": [value]})
                self.assertFalse(bad.run(archive(), "2026-10-11", ["bazi"], 7, "self")["artifacts"])

    def test_domain_any_payload_cannot_contain_nonfinite_values(self):
        feature = {"id": "f", "feature_key": "bazi.example", "value": {"nested": [float("nan")]},
                   "artifact_id": "a", "path": "/data/example", "owner_user_id": "owner-a",
                   "subject_id": "self", "revision": 7, "branch_id": "b", "time_scale": "natal"}
        with self.assertRaises(ValueError): CalculationFeature.model_validate(feature)
        feature["value"] = 1; feature["revision"] = True
        with self.assertRaises(ValueError): CalculationFeature.model_validate(feature)

    def test_sampling_is_explicit_and_never_continuous_coverage(self):
        for precision, extra, count in (("approximate", {"time_uncertainty_minutes": 20}, 3),
                                        ("interval", {"time_interval": {"start": "2012-05-03 12:00", "end": "2012-05-03 14:00"}}, 5),
                                        ("unknown", {}, 5)):
            with self.subTest(precision=precision):
                a = archive(); a["user"]["birth"].update(time_precision=precision, **extra)
                result = self.adapter.run(a, "2026-10-11", ["bazi"], 7, "self")
                self.assertEqual(len(result["branches"]), count, result["errors"])
                self.assertTrue(all(b["coverage"] == "sampled_not_continuous" for b in result["branches"]))
                self.assertTrue(all(f["stability"] in ("sampled_stable", "conditional") for f in result["features"].values()))

    def test_tarot_helper_uses_frozen_revealed_view_and_separate_revisions(self):
        draw = ready_draw(); out = self.registry.tarot_claims(draw, "owner-a", "self", 7)
        self.assertEqual(out["gaps"], []); self.assertTrue(out["claims"])
        claim = out["claims"][0]
        self.assertEqual(claim["revision"], 7)
        artifact = next(iter(out["artifacts"].values()))
        self.assertEqual(artifact["data"]["draw_revision"], 2)
        self.assertNotIn("question", artifact["data"])
        self.assertTrue(self.registry.validate_claim(claim, out["features"], out["context"], out["artifacts"])["eligible"])
        self.assertTrue(self.registry.revalidate_claims({"artifacts": {}, "features": {}, "profiles": {}}, out["claims"], out)["eligible"])

    def test_tarot_hidden_relabelled_revised_or_revoked_view_is_rejected(self):
        cases = [(lambda d: d.update(status="pending_reveal"), "DRAW_MISMATCH"),
                 (lambda d: d["cards"][0].update(revealed=False), "DRAW_MISMATCH"),
                 (lambda d: d["cards"][0]["card"].update(upright="必定成功"), "DRAW_MISMATCH"),
                 (lambda d: d["cards"][0].update(card_id="major-00"), "DRAW_MISMATCH"),
                 (lambda d: d.update(context_revoked=True), "AUTH_SCOPE_ERROR"),
                 (lambda d: d.update(subject_id="other"), "AUTH_SCOPE_ERROR"),
                 (lambda d: d.update(meaning_version="future-version"), "RULE_GAP"),
                 (lambda d: d.update(revision=True), "DRAW_MISMATCH")]
        for mutation, code in cases:
            d = ready_draw(); mutation(d)
            out = self.registry.tarot_claims(d, "owner-a", "self", 7)
            self.assertFalse(out["claims"]); self.assertEqual(out["gaps"][0]["status"], code)

    def test_tarot_every_card_orientation_uses_exact_catalog_meaning(self):
        for stable_id in self.registry._cards:
            for orientation in ("upright", "reversed"):
                d = ready_draw(); d["cards"][0].update(card_id=stable_id, orientation=orientation, card=card(stable_id))
                out = self.registry.tarot_claims(d, "owner-a", "self", 7)
                self.assertEqual(out["gaps"], [], stable_id)
                self.assertIn(self.registry._cards[stable_id][orientation], out["claims"][0]["text"])


REAL_CHARTS = all(has_dependency(name) for name in ("lunar_python", "swisseph", "py_iztro", "pythonmonkey"))


@unittest.skipUnless(REAL_CHARTS, "requires isolated requirements-charts.lock environment")
class RealCalculationExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ChartAdapter("owner-a", python=CHART_PYTHON)
        cls.result = cls.adapter.run(archive(), "2026-10-11", ["bazi", "ziwei", "astro"], 7, "self")
        cls.registry = KnowledgeRegistry.load_builtin()
        if cls.result["errors"]: raise AssertionError(cls.result["errors"])

    def test_every_released_chart_rule_declares_and_revalidates(self):
        out = self.registry.claims_for(self.result, "owner-a", "self", 7, "study", "all", "2026-10-11")
        self.assertEqual(out["gaps"], [])
        expected = {r.rule_id for r in self.registry._rules.values() if r.system != "tarot"}
        self.assertEqual({c["rule_id"] for c in out["claims"]}, expected)
        self.assertTrue(self.registry.revalidate_claims(self.result, out["claims"])["eligible"])
        for claim in out["claims"]:
            context = {key: claim[key] for key in ("owner_user_id", "subject_id", "revision", "branch_id", "time_scale")}
            context["target_date"] = "2026-10-11"
            scoped = {f["feature_key"]: f for f in self.result["features"].values()
                      if f["artifact_id"] == claim["feature_refs"][0]["artifact_id"]}
            self.assertTrue(self.registry.validate_claim(claim, scoped, context, self.result["artifacts"])["eligible"], claim["rule_id"])
            tampered = deepcopy(claim); tampered["text"] += " 因此必定成功"
            self.assertFalse(self.registry.validate_claim(tampered, scoped, context, self.result["artifacts"])["eligible"])
            self.assertFalse(self.registry.revalidate_claims(self.result, [tampered])["eligible"])

    def test_time_layers_do_not_borrow_a_daily_snapshot_for_yearly_or_monthly(self):
        for scope, expected in (("natal", {"natal"}), ("daily", {"daily", "daily_snapshot", "daily_transit_snapshot"}),
                                ("monthly", {"monthly"}), ("yearly", {"yearly"})):
            out = self.registry.claims_for(self.result, "owner-a", "self", 7, "study", scope, "2026-10-11")
            self.assertTrue(out["claims"])
            self.assertTrue(all(c["time_scale"] in expected for c in out["claims"]))
            if scope in ("monthly", "yearly"):
                self.assertTrue(any(g["status"] == "RULE_GAP" and g.get("system") == "astro" for g in out["gaps"]))

    def test_canonical_claims_survive_json_object_key_reordering(self):
        # Actual JSONB persistence changes object order, never ordered arrays.
        reordered = json.loads(json.dumps(self.result, sort_keys=True, ensure_ascii=False))
        original = self.registry.claims_for(self.result, "owner-a", "self", 7, "study", "all", "2026-10-11")
        fresh = self.registry.claims_for(reordered, "owner-a", "self", 7, "study", "all", "2026-10-11")
        self.assertEqual({c["claim_id"]: c for c in original["claims"]}, {c["claim_id"]: c for c in fresh["claims"]})
        self.assertTrue(self.registry.revalidate_claims(reordered, original["claims"])["eligible"])

    def test_education_is_an_explicit_study_alias(self):
        a = deepcopy(archive()); a["calculation_topic"] = "education"
        result = self.adapter.run(a, "2026-10-11", ["ziwei"], 7, "self")
        self.assertFalse(result["errors"])
        self.assertEqual(next(iter(result["artifacts"].values()))["data"]["selected_topic"]["topic"], "study")
        out = self.registry.claims_for(result, "owner-a", "self", 7, "education", "natal", "2026-10-11")
        self.assertTrue(out["claims"])
        self.assertEqual(self.registry.select("bazi", "education"), self.registry.select("bazi", "study"))

    def test_target_year_and_month_follow_date_and_solar_terms(self):
        result = self.adapter.run(archive(), "2025-01-02", ["bazi"], 7, "self")
        self.assertFalse(result["errors"])
        data = next(iter(result["artifacts"].values()))["data"]
        self.assertEqual(data["target_year"]["ganzhi"], "甲辰")
        self.assertEqual(data["target_year"]["period_start"][:4], "2024")
        self.assertEqual(data["target_year"]["period_end_exclusive"][:4], "2025")
        self.assertEqual(data["target_month"]["ganzhi"], data["day"]["month_ganzhi"])
        for layer in ("target_year", "target_month"):
            period = data[layer]
            sample = datetime.fromisoformat(period["sample_at"])
            self.assertLessEqual(datetime.fromisoformat(period["period_start"]), sample)
            self.assertLess(sample, datetime.fromisoformat(period["period_end_exclusive"]))
        self.assertEqual({x["year"] for x in data["target_liunian"]}, set(range(2023, 2033)))

    def test_actual_provenance_contains_returned_flags_and_engine_versions(self):
        profiles = {p["system"]: p for p in self.result["profiles"].values()}
        self.assertTrue(all(p["versions"].get("source_sha256") and all(len(h) == 64 for h in p["versions"]["source_sha256"].values()) for p in profiles.values()))
        astro = profiles["astro"]["actual_method"]
        self.assertIn("returned_flags", astro)
        self.assertEqual(astro["ephemeris"], ["Moshier"])
        self.assertEqual(astro["houses"], "Placidus")
        self.assertFalse(profiles["ziwei"]["versions"]["upstream_version_independently_verified"])

    def test_scope_revision_and_profile_changes_are_rejected(self):
        wrong = self.registry.claims_for(self.result, "other-owner", "self", 7, "study", "natal", "2026-10-11")
        self.assertFalse(wrong["claims"])
        self.assertTrue(all(g["status"] == "AUTH_SCOPE_ERROR" for g in wrong["gaps"]))
        wrong = self.registry.claims_for(self.result, "owner-a", "self", 8, "study", "natal", "2026-10-11")
        self.assertFalse(wrong["claims"])
        changed = deepcopy(self.result)
        for profile in changed["profiles"].values(): profile["branch_id"] = "different-branch"
        self.assertFalse(self.registry.claims_for(changed, "owner-a", "self", 7)["claims"])
        self.assertEqual(self.registry.claims_for(self.result, "owner-a", "self", 7, target_date="2027-10-11")["gaps"][0]["status"], "SCOPE_MISMATCH")

    def test_false_transit_geometry_has_no_claim(self):
        changed = deepcopy(self.result)
        artifact = next(a for a in changed["artifacts"].values() if a["system"] == "astro")
        self.assertTrue(artifact["data"]["transits"]["aspects_to_natal"])
        artifact["data"]["transits"]["aspects_to_natal"][0]["orb"] += 1
        for feature in changed["features"].values():
            if feature["feature_key"] == "astro.transits": feature["value"] = deepcopy(artifact["data"]["transits"])
        out = self.registry.claims_for(changed, "owner-a", "self", 7, "study", "daily", "2026-10-11")
        self.assertFalse(any(c["system"] == "astro" for c in out["claims"]))
        self.assertTrue(any(g["status"] == "REFERENCE_ERROR" for g in out["gaps"]))

    def test_same_artifact_and_feature_forgery_cannot_change_ten_gods(self):
        changed = deepcopy(self.result)
        artifact = next(a for a in changed["artifacts"].values() if a["system"] == "bazi")
        gods = artifact["data"]["ten_gods"]
        actual = gods["year"]["hidden_stems"][0]["ten_god"]
        gods["year"]["hidden_stems"][0]["ten_god"] = "正财" if actual != "正财" else "七杀"
        for feature in changed["features"].values():
            if feature["feature_key"] == "bazi.ten_gods": feature["value"] = deepcopy(gods)
        out = self.registry.claims_for(changed, "owner-a", "self", 7, "study", "natal", "2026-10-11")
        self.assertFalse(any(c["rule_id"] == "bazi.natal.hidden-ten-gods.v1" for c in out["claims"]))
        self.assertTrue(any(g["status"] == "REFERENCE_ERROR" for g in out["gaps"]))

    def test_same_artifact_and_feature_forgery_cannot_invent_branch_combination(self):
        changed = deepcopy(self.result)
        artifact = next(a for a in changed["artifacts"].values() if a["system"] == "bazi")
        relation = artifact["data"]["relations"]
        relation["pair_relations"].append({"from": "year", "to": "month", "ganzhi": [artifact["data"]["pillars"][name]["ganzhi"] for name in ("year", "month")],
                                          "relations": ["六合"], "transformation_asserted": False})
        for feature in changed["features"].values():
            if feature["feature_key"] == "bazi.relations": feature["value"] = deepcopy(relation)
        out = self.registry.claims_for(changed, "owner-a", "self", 7, "study", "natal", "2026-10-11")
        self.assertFalse(any(c["rule_id"] == "bazi.natal.raw-relations.v1" for c in out["claims"]))
        self.assertTrue(any(g["status"] == "REFERENCE_ERROR" for g in out["gaps"]))


if __name__ == "__main__": unittest.main()
