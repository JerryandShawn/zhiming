"""Offline glossary tests use immutable Git fixtures and ignored authoring output."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEB = next(
    path for path in Path(__file__).resolve().parents if path.name == "web" and (path / "package.json").is_file()
)
sys.path.insert(0, str(WEB / "scripts"))
try:
    exporter = importlib.import_module("export_study_glossary")
    project_glossary = importlib.import_module("study_glossary").project_glossary
    schema = importlib.import_module("study_schema")
    StudyExportError, parse, validate = schema.StudyExportError, schema.parse, schema.validate
finally:
    sys.path.pop(0)

HERE = WEB / "test-results"
ERROR = "^study_glossary_invalid$"


class GlossaryExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        HERE.mkdir(exist_ok=True)
        cls.raw = {
            path: subprocess.run(
                ["git", "show", f"{exporter.FROZEN_COMMIT}:{path}"],
                cwd=exporter.REPOSITORY,
                check=True,
                capture_output=True,
            ).stdout
            for path in exporter.INPUTS
        }
        cls.tree = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", exporter.FROZEN_COMMIT, "--"],
            cwd=exporter.REPOSITORY,
            check=True,
            capture_output=True,
        ).stdout

    def values(self):
        return {path: parse(raw) for path, raw in self.raw.items()}

    def project(self, values=None, paths=None):
        values = self.values() if values is None else values
        tree = set(self.tree.decode("utf8").splitlines()) if paths is None else paths
        return project_glossary(
            values[exporter.TERMS],
            values[exporter.SOURCES],
            values[exporter.TERMS_SCHEMA],
            values[exporter.SOURCES_SCHEMA],
            tree,
        )

    def reject(self, values):
        before = copy.deepcopy(values)
        with self.assertRaisesRegex(StudyExportError, ERROR):
            self.project(values)
        self.assertEqual(values, before)

    def reader(self, replacements=None, commit=None, tree=None):
        bodies = {**self.raw, **(replacements or {})}
        selected = exporter.FROZEN_COMMIT if commit is None else commit

        def read(*arguments):
            if arguments == ("rev-parse", "--verify", exporter.FROZEN_COMMIT + "^{commit}"):
                return (selected + "\n").encode("ascii")
            if arguments == ("ls-tree", "-r", "--name-only", selected, "--"):
                return self.tree if tree is None else tree
            for path, raw in bodies.items():
                if arguments == ("show", f"{selected}:{path}"):
                    return raw
            raise AssertionError("Unexpected Git operation")

        return read

    def test_actual_212_terms_and_39_sources_keep_stage_and_do_not_mutate_inputs(self):
        values = self.values()
        before = copy.deepcopy(values)
        terms, sources = self.project(values)
        self.assertEqual(terms["entry_count"], 212)
        self.assertEqual(terms["system_counts"], {"bazi": 72, "ziwei": 55, "astro": 50, "tarot": 35})
        self.assertEqual(len(sources["sources"]), 39)
        self.assertEqual(terms["stage"], "draft_complete_200_for_review")
        self.assertEqual(terms["review_tag"], "v1_ready_editorial_reviewed")
        self.assertEqual(values, before)
        self.assertEqual(terms, values[exporter.TERMS])
        self.assertEqual(sources, values[exporter.SOURCES])

    def test_returned_values_are_independent_including_nested_sources_and_differences(self):
        values = self.values()
        first, registry = self.project(values)
        first["entries"][0]["school_differences"][0]["note"] = "CHANGED"
        registry["sources"][0]["title"] = "CHANGED"
        second, second_registry = self.project(values)
        self.assertNotIn("CHANGED", json.dumps([second, second_registry]))

    def test_declared_count_distribution_and_boolean_numbers_are_rejected(self):
        for field, change in (
            ("entry_count", 211),
            ("entry_count", True),
            ("planned_minimum_entries", True),
            ("system_counts", {"bazi": 73, "ziwei": 54, "astro": 50, "tarot": 35}),
        ):
            with self.subTest(field=field):
                values = self.values()
                values[exporter.TERMS][field] = change
                self.reject(values)

    def test_duplicate_id_normalized_term_and_alias_are_not_counted_as_new_terms(self):
        for field, value in (
            ("term_id", "bazi-day-master"),
            ("term", "日主"),
            ("aliases", [" 日 元 "]),
            ("aliases", ["日主"]),
        ):
            with self.subTest(field=field, value=value):
                values = self.values()
                # Exact aliases are normalized by NFKC/casefold and whitespace,
                # while meaningful internal spaces are not silently deleted.
                values[exporter.TERMS]["entries"][1][field] = value if value != [" 日 元 "] else [" 日元 "]
                self.reject(values)

    def test_id_system_disagreement_and_unknown_definition_kind_are_rejected(self):
        for field, value in (("term_id", "astro-day-master"), ("system", "unknown"), ("definition_kind", "prediction")):
            with self.subTest(field=field):
                values = self.values()
                values[exporter.TERMS]["entries"][0][field] = value
                self.reject(values)

    def test_cross_system_homonyms_remain_separate_candidates(self):
        values = self.values()
        astro = next(term for term in values[exporter.TERMS]["entries"] if term["system"] == "astro")
        astro["term"] = "日主"
        terms, _ = self.project(values)
        self.assertEqual({row["system"] for row in terms["entries"] if row["term"] == "日主"}, {"bazi", "astro"})

    def test_missing_term_source_school_source_and_registry_version_are_errors(self):
        for field in ("term", "school", "version"):
            with self.subTest(field=field):
                values = self.values()
                term = values[exporter.TERMS]["entries"][0]
                if field == "term":
                    term["sources"][0]["source_id"] = "not-registered"
                elif field == "school":
                    term["school_differences"][0]["source_ids"] = ["not-registered"]
                else:
                    values[exporter.TERMS]["source_registry_version"] = "p8-glossary-sources-v2"
                self.reject(values)

    def test_duplicate_source_ids_and_duplicate_example_text_are_rejected(self):
        values = self.values()
        values[exporter.SOURCES]["sources"].append(copy.deepcopy(values[exporter.SOURCES]["sources"][0]))
        self.reject(values)
        values = self.values()
        values[exporter.TERMS]["entries"][1]["example"] = values[exporter.TERMS]["entries"][0]["example"]
        self.reject(values)

    def test_unknown_root_entry_reference_school_and_source_keys_are_not_projected(self):
        for target in ("terms", "entry", "reference", "school", "sources", "source"):
            with self.subTest(target=target):
                values = self.values()
                term = values[exporter.TERMS]["entries"][0]
                row = {
                    "terms": values[exporter.TERMS],
                    "entry": term,
                    "reference": term["sources"][0],
                    "school": term["school_differences"][0],
                    "sources": values[exporter.SOURCES],
                    "source": values[exporter.SOURCES]["sources"][0],
                }[target]
                row["scope"] = {"owner_user_id": "PRIVATE_SENTINEL"}
                self.reject(values)

    def test_html_control_characters_and_script_sources_are_rejected(self):
        for value in (
            "<script>PRIVATE_SENTINEL</script>",
            "<img src=x onerror=PRIVATE_SENTINEL>",
            "白话\x00PRIVATE_SENTINEL",
            "白话\u202ePRIVATE_SENTINEL",
        ):
            with self.subTest(value=value):
                values = self.values()
                values[exporter.TERMS]["entries"][0]["plain_explanation"] = value
                self.reject(values)
        values = self.values()
        values[exporter.SOURCES]["sources"][0]["locator"] = "<script>PRIVATE_SENTINEL</script>"
        self.reject(values)

    def test_exact_audited_index_placeholder_is_literal_source_not_arbitrary_html(self):
        terms, sources = self.project()
        row = next(item for item in sources["sources"] if "<index>" in item["locator"])
        self.assertEqual(row["source_id"], "project-tarot-editorial")
        self.assertNotIn("<", json.dumps(terms, ensure_ascii=False))
        values = self.values()
        selected = next(item for item in values[exporter.SOURCES]["sources"] if "<index>" in item["locator"])
        selected["locator"] += "<svg>PRIVATE_SENTINEL</svg>"
        self.reject(values)

    def test_schema_text_minimums_and_types_are_enforced(self):
        for target, field, value in (
            ("term", "plain_explanation", "短" * 19),
            ("term", "example", "短" * 14),
            ("reference", "support_scope", "短" * 9),
            ("school", "note", "短" * 11),
            ("term", "pending_review", [None]),
            ("term", "aliases", [1]),
        ):
            with self.subTest(target=target, field=field):
                values = self.values()
                term = values[exporter.TERMS]["entries"][0]
                selected = {"term": term, "reference": term["sources"][0], "school": term["school_differences"][0]}[
                    target
                ]
                selected[field] = value
                self.reject(values)

    def test_source_paths_require_frozen_repository_membership_without_traversal(self):
        for path in (
            "../private.json",
            "/private.json",
            "C:/private.json",
            "mingjing_core\\private.py",
            "mingjing_core/not-published.py",
            "mingjing_core/./knowledge/x.json",
        ):
            with self.subTest(path=path):
                values = self.values()
                values[exporter.SOURCES]["sources"][0]["path"] = path
                self.reject(values)

    def test_source_urls_are_documentation_only_and_unknown_or_unsafe_urls_are_rejected(self):
        for url in (
            "javascript:alert(1)",
            "https://unreviewed.invalid/",
            "https://docs.iztro.com@private.invalid/",
            "https://docs.iztro.com/posts/palace#unreviewed",
        ):
            with self.subTest(url=url):
                values = self.values()
                values[exporter.SOURCES]["sources"][0]["url"] = url
                self.reject(values)
        values = self.values()
        values[exporter.SOURCES]["sources"][0]["path"] = None
        values[exporter.SOURCES]["sources"][0]["url"] = None
        self.reject(values)

    def test_complete_and_seed_stage_cannot_lie_about_count_or_review(self):
        for stage in ("draft_seed_10_pending_root_review", "UNREVIEWED_COMPLETE"):
            with self.subTest(stage=stage):
                values = self.values()
                values[exporter.TERMS]["stage"] = stage
                self.reject(values)
        values = self.values()
        del values[exporter.TERMS]["review_tag"]
        self.reject(values)

    def test_a_real_ten_term_seed_is_explicitly_incomplete_instead_of_relabelled_complete(self):
        values = self.values()
        terms = values[exporter.TERMS]
        sizes = {"bazi": 3, "ziwei": 3, "astro": 2, "tarot": 2}
        terms["entries"] = [
            item
            for system, count in sizes.items()
            for item in [row for row in terms["entries"] if row["system"] == system][:count]
        ]
        terms.update(stage="draft_seed_10_pending_root_review", entry_count=10, system_counts=sizes)
        del terms["review_tag"]
        public, _ = self.project(values)
        self.assertEqual(public["stage"], "draft_seed_10_pending_root_review")
        self.assertNotIn("review_tag", public)

    def test_parser_rejects_duplicate_keys_nonfinite_values_and_never_echoes_them(self):
        for raw in (b'{"scope":1,"scope":"PRIVATE_SENTINEL"}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b"{"):
            with self.subTest(raw=raw), self.assertRaisesRegex(StudyExportError, ERROR):
                parse(raw)

    def test_unsupported_schema_keywords_or_remote_refs_fail_closed_without_dereferencing(self):
        for schema in ({"$ref": "https://private.invalid/schema"}, {"not": {}}, {"format": "executable"}):
            with self.subTest(schema=schema), self.assertRaisesRegex(StudyExportError, ERROR):
                validate("example", schema)

    def test_new_output_contains_fixed_input_and_output_digests_without_modifying_sources(self):
        before = dict(self.raw)
        with tempfile.TemporaryDirectory(prefix="study-export-", dir=HERE) as directory:
            output = Path(directory) / "new"
            reader = mock.Mock(side_effect=self.reader())
            manifest = exporter.export_glossary(output, reader)
            self.assertEqual(manifest["source_commit"], exporter.FROZEN_COMMIT)
            self.assertEqual(manifest["entry_count"], 212)
            self.assertEqual(manifest["source_count"], 39)
            self.assertEqual(manifest["model_calls"], 0)
            self.assertEqual(manifest["source_urls_fetched"], 0)
            self.assertEqual(len(manifest["inputs"]), 4)
            self.assertEqual(reader.call_count, 6)
            self.assertEqual(
                {path.name for path in output.iterdir()}, {"terms_v1.json", "sources_v1.json", "manifest.json"}
            )
            for row in manifest["entries"]:
                raw = (output / row["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["sha256"])
                self.assertEqual(len(raw), row["bytes"])
            self.assertEqual(json.loads((output / "manifest.json").read_bytes()), manifest)
        self.assertEqual(self.raw, before)

    def test_existing_output_and_outside_web_paths_are_rejected_before_git_reads(self):
        with tempfile.TemporaryDirectory(prefix="study-export-", dir=HERE) as directory:
            output = Path(directory) / "existing"
            output.mkdir()
            marker = output / "terms_v1.json"
            marker.write_bytes(b"KEEP_EXISTING_OUTPUT")
            for path in (output, exporter.WEB, exporter.WEB.parent / "must-not-exist-study-output"):
                with self.subTest(path=str(path)):
                    reader = mock.Mock()
                    with self.assertRaisesRegex(StudyExportError, ERROR):
                        exporter.export_glossary(path, reader)
                    reader.assert_not_called()
            self.assertEqual(marker.read_bytes(), b"KEEP_EXISTING_OUTPUT")

    def test_changed_source_schema_or_commit_is_rejected_before_any_output(self):
        with tempfile.TemporaryDirectory(prefix="study-export-", dir=HERE) as directory:
            output = Path(directory) / "not-created"
            for path in exporter.INPUTS:
                with self.subTest(path=path), self.assertRaisesRegex(StudyExportError, ERROR):
                    exporter.export_glossary(output, self.reader({path: self.raw[path] + b" "}))
                self.assertFalse(output.exists())
            with self.assertRaisesRegex(StudyExportError, ERROR):
                exporter.export_glossary(output, self.reader(commit="1" * 40))
            self.assertFalse(output.exists())

    def test_missing_registered_local_source_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory(prefix="study-export-", dir=HERE) as directory:
            output = Path(directory) / "not-created"
            with self.assertRaisesRegex(StudyExportError, ERROR):
                exporter.export_glossary(output, self.reader(tree=b""))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
