"""Offline public projection tests use fixed synthetic Git objects, without engines."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEB = next(
    path for path in Path(__file__).resolve().parents if path.name == "web" and (path / "package.json").is_file()
)
PACKAGE = WEB / "scripts" / "learning_samples"
NAME = "_frontend_learning_projection"
SPEC = importlib.util.spec_from_file_location(NAME, PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)])
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[NAME] = MODULE
SPEC.loader.exec_module(MODULE)
exporter = importlib.import_module(NAME + ".export_learning_samples")
common = importlib.import_module(NAME + ".common")
integrity = importlib.import_module(NAME + ".chart_integrity")
learning_integrity = importlib.import_module(NAME + ".learning_integrity")
projection = importlib.import_module(NAME + ".projection")


def replace_ids(value: object, mapping: dict[str, str]) -> object:
    if type(value) is str:
        return mapping.get(value, value)
    if type(value) is list:
        return [replace_ids(item, mapping) for item in value]
    if type(value) is dict:
        return {key: replace_ids(item, mapping) for key, item in value.items()}
    return value


def resign(chart: dict) -> dict:
    mapping = {}
    for row in chart["documents"]:
        content = {key: row[key] for key in ("kind", "source_sha256", "payload")}
        mapping[row["document_id"]] = "doc-" + common.digest({"scope": chart["scope"], **content})
    chart = replace_ids(chart, mapping)
    documents = {row["document_id"]: row for row in chart["documents"]}
    for row in chart["aliases"]["c"] + chart["aliases"]["r"]:
        row["value_sha256"] = common.digest(integrity.resolve_ref(documents, row["ref"]))
        reclaim(row)
    return chart


def reclaim(row: dict) -> None:
    claim = {key: row[key] for key in ("scope", "ref", "value_sha256", "branch_id", "basis")}
    claim.update({key: row[key] for key in ("rule_id", "rules_version") if key in row})
    row["claim_id"] = "demo-claim-" + common.digest(claim)


class LearningProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = {name: exporter.fixed_git(name) for name in exporter.EXPECTED}
        cls.values = {name: common.parse(raw) for name, raw in cls.raw.items()}

    def pair(self, system: str = "bazi") -> tuple[dict, dict]:
        return (
            copy.deepcopy(self.values[f"learning-ayuan-{system}.json"]),
            copy.deepcopy(self.values[f"ayuan_{system}.json"]),
        )

    def invalid(self, function, *args) -> None:
        with self.assertRaisesRegex(ValueError, "^" + common.ERROR + "$"):
            function(*args)

    def test_all_three_fixed_cases_project_deterministically_without_mutating_inputs(self) -> None:
        for system, count in (("bazi", 11), ("ziwei", 2), ("astro", 2)):
            with self.subTest(system=system):
                learning, chart = self.pair(system)
                before = copy.deepcopy((learning, chart))
                result = projection.project_learning(learning, chart, system)
                self.assertEqual(len(result["cards"]), count)
                self.assertEqual(result, projection.project_learning(learning, chart, system))
                self.assertEqual((learning, chart), before)
                self.assertEqual(result["effects"]["model_calls"], 0)
                self.assertEqual(result["effects"]["writes"], 0)

    def test_original_noncontinuous_aliases_and_case_document_ownership_are_preserved(self) -> None:
        outputs = {}
        for system in common.SYSTEMS:
            learning, chart = self.pair(system)
            output = projection.project_learning(learning, chart, system)
            expected = learning["aliases"]["c"] + learning["aliases"]["r"]
            self.assertEqual([row["alias"] for row in output["evidence"]], [row["alias"] for row in expected])
            self.assertEqual([row["claim_id"] for row in output["evidence"]], [row["claim_id"] for row in expected])
            self.assertEqual(
                [row["document_id"] for row in output["evidence"]], [row["ref"]["document_id"] for row in expected]
            )
            outputs[system] = output
        self.assertEqual(outputs["astro"]["cards"][0]["c_aliases"], ["c2"])
        self.assertEqual(outputs["bazi"]["cards"][-1]["c_aliases"], ["c26", "c27", "c28"])
        self.assertNotEqual(
            outputs["bazi"]["cards"][0]["evidence_refs"][0]["document_id"],
            outputs["ziwei"]["cards"][0]["evidence_refs"][0]["document_id"],
        )

    def test_no_raw_observation_scope_birth_pointer_or_original_payload_reaches_public_output(self) -> None:
        forbidden = {
            "observed",
            "scope",
            "owner_user_id",
            "subject_id",
            "operation_id",
            "birth",
            "request",
            "time_basis",
            "documents",
            "payload",
            "path",
            "branch_id",
        }

        def inspect(value: object) -> None:
            if type(value) is dict:
                self.assertFalse(forbidden.intersection(value))
                for item in value.values():
                    inspect(item)
            elif type(value) is list:
                for item in value:
                    inspect(item)

        for system in common.SYSTEMS:
            learning, chart = self.pair(system)
            output = projection.project_learning(learning, chart, system)
            inspect(output)
            serialized = json.dumps(output, ensure_ascii=False)
            for sentinel in (
                "1994-03-12",
                "08:20",
                "104.07",
                "30.67",
                "synthetic-owner",
                "synthetic-subject",
                "/charts/",
                "/time_basis/",
                "下面的实际输入",
                "实际候选并列核对",
            ):
                self.assertNotIn(sentinel, serialized)

    def test_learning_text_observed_school_source_and_identity_are_bound_to_the_original_template(self) -> None:
        for field, value in (
            ("text", "PRIVATE_SENTINEL"),
            ("observed", {"birth": "PRIVATE_SENTINEL"}),
            ("school", "unreviewed school"),
            ("source_refs", ["https://untrusted.invalid"]),
            ("point_id", "other-point"),
            ("c_aliases", ["c1"]),
            ("citations", "〔c1〕"),
        ):
            with self.subTest(field=field):
                learning, chart = self.pair()
                learning["points"][0][field] = value
                self.invalid(projection.project_learning, learning, chart, "bazi")

    def test_learning_alias_rows_rule_hits_and_all_source_document_ids_must_be_original(self) -> None:
        for field in ("aliases", "rule_hits", "source_document_ids"):
            learning, chart = self.pair("astro")
            if field == "aliases":
                learning[field]["c"][0]["claim_id"] = "demo-claim-" + "0" * 64
            elif field == "rule_hits":
                learning[field][0]["met"] = False
            else:
                self.assertEqual(len(learning[field]), 4)
                learning[field] = learning[field][:2]
            self.invalid(projection.project_learning, learning, chart, "astro")

    def test_wrong_document_hash_alias_value_or_claim_are_rejected(self) -> None:
        for field in ("document", "value", "claim"):
            learning, chart = self.pair()
            if field == "document":
                chart["documents"][0]["document_id"] = "doc-" + "0" * 64
            elif field == "value":
                chart["aliases"]["c"][0]["value_sha256"] = "0" * 64
            else:
                chart["aliases"]["c"][0]["claim_id"] = "demo-claim-" + "0" * 64
            self.invalid(projection.project_learning, learning, chart, "bazi")

    def test_rehashed_false_rule_wrong_branch_version_and_evidence_order_are_rejected(self) -> None:
        _, original = self.pair()
        false = copy.deepcopy(original)
        row = false["aliases"]["r"][0]
        documents = {item["document_id"]: item for item in false["documents"]}
        integrity.resolve_ref(documents, row["ref"])["met"] = False
        self.invalid(integrity.verify_chart, resign(false), "bazi")
        for field, value in (
            ("branch_id", "other-branch"),
            ("basis", "standard"),
            ("rules_version", "wrong-version"),
            ("evidence_aliases", ["c3"]),
        ):
            chart = copy.deepcopy(original)
            chart["aliases"]["r"][0][field] = value
            reclaim(chart["aliases"]["r"][0])
            self.invalid(integrity.verify_chart, chart, "bazi")
        boundary = copy.deepcopy(original)
        boundary["aliases"]["r"][-1]["evidence_aliases"].reverse()
        self.invalid(integrity.verify_chart, boundary, "bazi")

    def test_boundary_rule_retains_its_actual_utc_input_evidence_without_forcing_equal_bases(self) -> None:
        learning, chart = self.pair()
        documents, aliases = integrity.verify_chart(chart, "bazi")
        self.assertEqual(len(documents), 1)
        rule = aliases["r10"]
        self.assertEqual(rule["basis"], "true_solar")
        self.assertTrue(all(aliases[name]["basis"] == "actual_UTC" for name in rule["evidence_aliases"]))
        result = projection.project_learning(learning, chart, "bazi")
        boundary = next(row for row in result["evidence"] if row["alias"] == "r10")
        self.assertEqual([row["alias"] for row in boundary["evidence_refs"]], ["c26", "c27", "c28"])

    def test_primary_view_diagnostics_and_cross_case_inputs_are_not_interchangeable(self) -> None:
        learning, chart = self.pair()
        chart["view"]["primary"] = chart["view"]["diagnostics"][:1]
        self.invalid(projection.project_learning, learning, chart, "bazi")
        _, ziwei = self.pair("ziwei")
        self.invalid(projection.project_learning, learning, ziwei, "bazi")
        learning, chart = self.pair()
        learning["scope"]["operation_id"] = "synthetic-other-case"
        self.invalid(projection.project_learning, learning, chart, "bazi")

    def test_strict_pointer_and_nonfinite_or_boolean_scope_rejections(self) -> None:
        self.assertEqual(common.pointer({"a/b": {"~": [7]}}, "/a~1b/~0/0"), 7)
        for path in ("/a~2b", "/rows/01", "/rows/-1", "/rows/-", "/rows/2"):
            self.invalid(common.pointer, {"rows": [1]}, path)
        self.assertFalse(common.same(True, 1))
        for value in (True, float("nan"), float("inf")):
            _, chart = self.pair()
            chart["scope"]["revision"] = value
            self.invalid(integrity.verify_chart, chart, "bazi")
        self.invalid(common.parse, b'{"duplicate":1,"duplicate":2}')

    def test_export_uses_six_fixed_blobs_and_only_creates_a_new_public_directory(self) -> None:
        reader = mock.Mock(side_effect=lambda name: self.raw[name])
        with tempfile.TemporaryDirectory(dir=WEB / "test-results", prefix="learning-owned-") as temporary:
            root = Path(temporary).resolve()
            self.assertIn(WEB, root.parents)
            output = root / "new"
            manifest = exporter.export_samples(output, reader)
            self.assertEqual(reader.call_args_list, [mock.call(name) for name in exporter.EXPECTED])
            self.assertEqual(manifest["source_commit"], common.COMMIT)
            self.assertTrue(manifest["synthetic_only"])
            self.assertEqual(manifest["model_calls"], 0)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted([entry["file"] for entry in manifest["entries"]] + ["manifest.json"]),
            )
            for entry in manifest["entries"]:
                raw = (output / entry["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
                self.assertEqual(json.loads(raw)["provenance"]["source_commit"], common.COMMIT)

    def test_output_overwrite_escape_and_source_hash_changes_are_refused_before_writing(self) -> None:
        with tempfile.TemporaryDirectory(dir=WEB / "test-results", prefix="learning-owned-") as temporary:
            root = Path(temporary).resolve()
            self.assertIn(WEB, root.parents)
            reader = mock.Mock(side_effect=lambda name: self.raw[name])
            self.invalid(exporter.export_samples, root, reader)
            reader.assert_not_called()
            self.invalid(exporter.export_samples, WEB, reader)
            self.invalid(exporter.export_samples, WEB.parent / "outside-learning", reader)
            reader.assert_not_called()
            changed = dict(self.raw)
            changed[next(iter(changed))] += b" "
            target = root / "must-not-exist"
            self.invalid(exporter.export_samples, target, lambda name: changed[name])
            self.assertFalse(target.exists())
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
