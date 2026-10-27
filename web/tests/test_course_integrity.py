"""Offline contract tests: only immutable synthetic Git objects, no model or database."""

from __future__ import annotations

import copy
import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB / "scripts"))
bundle = importlib.import_module("course_bundle")
integrity = importlib.import_module("course_integrity")
sys.path.pop(0)


class CourseIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, cls.hashes = bundle.load_bundle()

    def setUp(self):
        self.values = copy.deepcopy(self.original)
        self.curriculum = self.values[bundle.PREFIX + "curriculum_v1.json"]
        self.lesson = self.values[bundle.PREFIX + "lessons/lesson-01.json"]

    def invalid(self):
        with self.assertRaisesRegex(ValueError, "^course_bundle_invalid$"):
            integrity.verify_bundle(self.values, self.hashes)

    def test_all_twenty_lessons_and_forty_questions_bind_to_three_real_synthetic_cases(
        self,
    ):
        result = integrity.verify_bundle(self.values, self.hashes)
        self.assertEqual(len(result["lessons"]), 20)
        self.assertEqual(sum(len(item["quiz"]) for item in result["lessons"]), 40)
        self.assertEqual(len(result["evidence"]), 20)
        self.assertEqual(len(result["source_ids"]), 39)
        self.assertEqual(
            [
                item["c_alias"]
                for item in self.curriculum["evidence"]
                if item["case_id"] == "ayuan-astro"
            ],
            ["c7"],
        )

    def test_reader_rejects_changed_source_before_any_projection(self):
        def reader(path):
            if path == integrity.TERMS:
                return b'{"SECRET_CHANGED_BODY":true}'
            return bundle.git_read(path)

        with self.assertRaisesRegex(ValueError, "^course_bundle_invalid$"):
            bundle.load_bundle(reader)

    def test_manifest_pin_does_not_accept_a_new_count_or_path(self):
        raw = bundle.git_read(bundle.MANIFEST)
        value = json.loads(raw)
        value["assets"][0]["path"] = "../../SECRET"
        with self.assertRaisesRegex(ValueError, "^course_bundle_invalid$"):
            bundle.load_bundle(lambda _path: json.dumps(value).encode())

    def test_published_schema_is_not_allowed_to_resolve_external_references(self):
        self.values["docs/v4/contracts/learning_lessons.schema.json"]["$ref"] = (
            "https://invalid.test/SECRET"
        )
        with mock.patch(
            "socket.socket", side_effect=AssertionError("Network forbidden")
        ):
            self.invalid()

    def test_changed_case_digest_is_rejected(self):
        self.curriculum["cases"][0]["chart_sha256"] = "0" * 64
        self.invalid()

    def test_malformed_schema_never_echoes_source_content(self):
        self.values["docs/v4/contracts/learning_lessons.schema.json"]["oneOf"] = (
            "SECRET_BAD_SCHEMA"
        )
        self.invalid()

    def test_quiz_ids_cannot_collide_across_lessons(self):
        self.lesson["quiz"][0]["quiz_id"] = "lesson-02-q1"
        self.invalid()

    def test_cross_case_scope_is_not_rebound_from_a_similarly_named_alias(self):
        self.curriculum["cases"][0]["scope"] = self.curriculum["cases"][1]["scope"]
        self.invalid()

    def test_cross_case_evidence_cannot_use_another_cases_c3(self):
        self.curriculum["evidence"][0]["case_id"] = "ayuan-ziwei"
        self.invalid()

    def test_expected_value_is_checked_against_the_actual_alias_pointer(self):
        self.curriculum["evidence"][0]["expected"] = "SECRET_WRONG_ANSWER"
        self.invalid()

    def test_false_is_not_number_zero(self):
        row = next(
            item for item in self.curriculum["evidence"] if item["expected"] is False
        )
        row["expected"] = 0
        self.invalid()

    def test_invalid_pointer_escape_is_not_forgiven(self):
        self.curriculum["evidence"][0]["relative_path"] = "/pillars/~2"
        self.invalid()

    def test_noncanonical_array_index_is_not_forgiven(self):
        row = next(
            item
            for item in self.curriculum["evidence"]
            if item["evidence_id"] == "strength_a"
        )
        row["relative_path"] = "/p8/strength/methods/00/score"
        self.invalid()

    def test_diagnostic_or_basis_alias_does_not_replace_the_primary(self):
        row = next(
            item for item in self.curriculum["evidence"] if item["role"] == "basis"
        )
        row["role"] = "primary"
        self.invalid()

    def test_rule_evidence_requires_a_real_rule(self):
        row = next(
            item for item in self.curriculum["evidence"] if item["role"] == "rule_input"
        )
        row["r_aliases"] = []
        self.invalid()

    def test_rule_inputs_must_belong_to_the_declared_rule(self):
        row = next(
            item
            for item in self.curriculum["evidence"]
            if item["evidence_id"] == "seal_exposed"
        )
        row["r_aliases"] = ["r1"]
        self.invalid()

    def test_source_registry_digest_drift_is_not_silently_accepted(self):
        self.curriculum["source_registry"]["sha256"] = "0" * 64
        self.invalid()

    def test_future_prerequisite_is_not_a_completed_dependency(self):
        self.lesson["prerequisite_ids"] = ["lesson-20"]
        self.invalid()

    def test_duplicate_lesson_cannot_claim_the_twenty_lesson_count(self):
        self.curriculum["lessons"][1] = copy.deepcopy(self.curriculum["lessons"][0])
        self.invalid()

    def test_duplicate_option_ids_are_not_valid_choices(self):
        options = self.lesson["quiz"][0]["options"]
        options[1]["option_id"] = options[0]["option_id"]
        self.invalid()

    def test_shuffling_options_preserves_the_stable_answer_id(self):
        for lesson in [
            value for key, value in self.values.items() if "/lessons/lesson-" in key
        ]:
            for quiz in lesson["quiz"]:
                quiz["options"].reverse()
        result = integrity.verify_bundle(self.values, self.hashes)
        self.assertEqual(result["lessons"][0]["quiz"][0]["correct_option_id"], "a")

    def test_changed_correct_option_is_rejected(self):
        self.lesson["quiz"][0]["correct_option_id"] = "b"
        self.invalid()

    def test_duplicate_correct_value_is_not_a_distinct_distractor(self):
        quiz = self.lesson["quiz"][0]
        quiz["options"][1]["value"] = quiz["basis"]["expected"]
        self.invalid()

    def test_concept_cannot_fabricate_a_chart_citation(self):
        self.lesson["quiz"][1]["explanation"] += "〔c3〕"
        self.invalid()

    def test_undeclared_source_cannot_be_used_for_a_concept(self):
        self.lesson["quiz"][1]["basis"]["source_ids"] = ["UNKNOWN_SOURCE"]
        self.invalid()

    def test_worked_example_must_keep_its_case_local_evidence(self):
        self.lesson["worked_examples"][0]["case_id"] = "ayuan-astro"
        self.invalid()

    def test_worked_example_cannot_link_an_unknown_learning_card(self):
        self.lesson["worked_examples"][0]["learning_point_ids"] = ["learning-999"]
        self.invalid()

    def test_prose_cannot_invent_a_new_short_reference(self):
        self.lesson["paragraphs"][0] += "〔c999〕"
        self.invalid()

    def test_no_calculator_model_database_or_source_urls_are_needed(self):
        with mock.patch(
            "socket.socket", side_effect=AssertionError("Network forbidden")
        ):
            result = integrity.verify_bundle(self.values, self.hashes)
        self.assertEqual(len(result["cases"]), 3)


if __name__ == "__main__":
    unittest.main()
