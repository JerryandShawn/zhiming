"""Actual member-to-context and member-to-ranking checks, without prediction claims."""

from __future__ import annotations

import copy
import json
import platform
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.benchmarks.daily_transit_samples import (  # noqa: E402
    sample_natal,
)
from mingjing_core.adapters.charts.benchmarks.handoff_offline import (  # noqa: E402
    offline_runtime,
)
from mingjing_core.adapters.charts.daily_transit import daily_transit  # noqa: E402
from mingjing_core.adapters.charts.tool_evidence import pointer  # noqa: E402
from mingjing_core.adapters.charts.window_search import window_search  # noqa: E402

DAYS = tuple(f"2026-10-{day}" for day in range(21, 28))
PURPOSE = "签约"


def member_layers(fact: dict, nodes: dict) -> dict[str, list[str]]:
    """Derive only from actual member IDs, independently of context/weight helpers."""
    allowed = {
        "natal": {"year", "month", "day", "hour"},
        "target": {"yearly", "monthly", "daily"},
    }
    derived: dict[str, list[str]] = {"natal": [], "target": []}
    seen = set()
    assert fact["members"]
    for member in fact["members"]:
        ident = member["id"]
        assert ident not in seen
        seen.add(ident)
        domain, separator, layer = ident.partition(".")
        assert separator == "." and domain in allowed and layer in allowed[domain]
        # Member identity must also match its real graph node, not just its label.
        for key in ("ganzhi", "stem", "branch"):
            assert member[key] == nodes[ident][key]
        derived[domain].append(layer)
    assert derived["natal"] and derived["target"]
    return derived


class DailyWindowMembersNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        platform.system()
        natal = sample_natal()
        before = copy.deepcopy(natal)
        cls.weights = json.loads(
            (ROOT / "mingjing_core/knowledge/p8_windows_v1.json").read_text("utf8")
        )
        with offline_runtime():
            # Fresh public daily calls provide an independent source for window copies.
            cls.daily = {day: daily_transit(natal, day) for day in DAYS}
            cls.window = window_search(
                natal, {"start_date": DAYS[0], "end_date": DAYS[-1]}, PURPOSE
            )
        assert natal == before

    def daily_relations(self):
        for day, result in self.daily.items():
            nodes = {
                node["id"]: node
                for node in result["data"]["bazi"]["interactions"]["nodes"]
            }
            for hit in result["rule_hits"]:
                context = hit["context"]
                if context["system"] == "bazi" and context["kind"] == "relation":
                    fact = pointer(result, hit["evidence_paths"][0])
                    yield day, context, fact, member_layers(fact, nodes)

    def test_daily_context_exactly_matches_real_member_domains_and_order(self) -> None:
        count = 0
        for day, context, fact, derived in self.daily_relations():
            with self.subTest(day=day, relation=fact["kind"], identity=fact["id"]):
                self.assertEqual(context["natal_pillars"], derived["natal"])
                self.assertEqual(context["target_layers"], derived["target"])
                self.assertEqual(context["relation"], fact["kind"])
                self.assertIs(context["complete"], fact.get("complete", True))
                self.assertIs(context["transformation_established"], False)
            count += 1
        self.assertGreater(count, 0)

    def test_window_factor_and_contribution_follow_actual_copied_members(self) -> None:
        self.assertEqual(self.window["data"]["weights"], self.weights)
        count = 0
        for hit in self.window["rule_hits"]:
            weighted = hit["context"]
            if weighted["family"] != "bazi_relation":
                continue
            observation = pointer(self.window, hit["evidence_paths"][0])
            day = self.daily[observation["date"]]
            native = day["rule_hits"][observation["daily_rule_index"]]
            self.assertEqual(observation["daily_document_id"], day["document_id"])
            self.assertEqual(observation["daily_hit"], native)
            for copied in observation["facts"]:
                self.assertEqual(copied["value"], pointer(day, copied["path"]))
            fact = pointer(day, native["evidence_paths"][0])
            nodes = {
                node["id"]: node
                for node in day["data"]["bazi"]["interactions"]["nodes"]
            }
            targets = member_layers(fact, nodes)["target"]
            factor = max(self.weights["layer_factors"][layer] for layer in targets)
            base = self.weights["purpose_weights"][PURPOSE]["bazi_relation"][
                fact["kind"]
            ]
            complete = fact.get("complete", True)
            expected = base * factor if complete else 0
            with self.subTest(day=observation["date"], relation=fact["kind"]):
                self.assertEqual(weighted["label"], fact["kind"])
                self.assertEqual(weighted["base_weight"], base)
                self.assertEqual(weighted["layer_factor"], factor)
                self.assertEqual(weighted["contribution"], expected)
                self.assertEqual(hit["contribution"], expected)
            count += 1
        self.assertGreater(count, 0)

    def test_fixed_week_exercises_multiple_kinds_layers_and_group_completeness(
        self,
    ) -> None:
        kinds, layers, factors, completeness = set(), set(), set(), set()
        multiple_target_layers = 0
        for _day, _context, fact, derived in self.daily_relations():
            kinds.add(fact["kind"])
            layers.update(derived["target"])
            factors.add(
                max(self.weights["layer_factors"][layer] for layer in derived["target"])
            )
            completeness.add(fact.get("complete", True))
            multiple_target_layers += len(derived["target"]) > 1
        self.assertGreaterEqual(len(kinds), 3)
        self.assertEqual(layers, {"yearly", "monthly", "daily"})
        self.assertEqual(factors, {1, 2, 3})
        self.assertEqual(completeness, {True, False})
        self.assertGreater(multiple_target_layers, 0)


if __name__ == "__main__":
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DailyWindowMembersNative)
    )
    print(
        json.dumps(
            {
                "tests": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
                "successful": result.wasSuccessful(),
            }
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
