"""Public course exports must stay isolated from the unchanged earlier assets."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB / "scripts"))
bundle = importlib.import_module("course_bundle")
projection = importlib.import_module("course_projection")
sys.path.pop(0)


def keys(value):
    if type(value) is dict:
        for key, child in value.items():
            yield key
            yield from keys(child)
    elif type(value) is list:
        for child in value:
            yield from keys(child)


class CourseProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values, cls.hashes = bundle.load_bundle()
        cls.projected = projection.project_course(cls.values, cls.hashes)

    def test_only_registered_teaching_text_and_stable_answers_are_public(self):
        result = self.projected
        self.assertEqual(len(result["lessons"]), 20)
        quizzes = [quiz for lesson in result["lessons"] for quiz in lesson["quiz"]]
        self.assertEqual(len(quizzes), 40)
        for quiz in quizzes:
            self.assertEqual(len(quiz["options"]), 3)
            self.assertIn(
                quiz["correct_option_id"], [row["option_id"] for row in quiz["options"]]
            )
            self.assertEqual(set(quiz["basis"]), {"kind"})
            self.assertTrue(
                all(set(row) == {"option_id", "text"} for row in quiz["options"])
            )

    def test_no_raw_chart_scope_pointer_or_observation_fields_are_exported(self):
        forbidden = {
            "scope",
            "operation_id",
            "documents",
            "request",
            "observed",
            "expected",
            "relative_path",
            "coordinate_datetime",
            "birth_datetime",
            "charts",
            "value",
        }
        self.assertFalse(set(keys(self.projected)) & forbidden)

    def test_new_astro_case_retains_c7_without_relabeling_old_assets(self):
        rows = [
            row for row in self.projected["evidence"] if row["case_id"] == "ayuan-astro"
        ]
        self.assertEqual([row["c_alias"] for row in rows], ["c7"])
        cases = {row["case_id"]: row for row in self.projected["cases"]}
        for row in self.projected["evidence"]:
            self.assertEqual(
                row["context_sha256"], cases[row["case_id"]]["context_sha256"]
            )
        self.assertEqual(len({row["context_sha256"] for row in cases.values()}), 3)

    def test_provenance_pins_manifest_commit_and_all_input_hashes(self):
        provenance = self.projected["provenance"]
        self.assertEqual(provenance["source_commit"], bundle.COMMIT)
        self.assertEqual(provenance["manifest_sha256_lf_utf8"], bundle.MANIFEST_SHA)
        self.assertEqual(provenance["input_sha256_lf_utf8"], self.hashes)
        self.assertEqual(len(self.hashes), 32)

    def test_every_course_source_is_a_review_labeled_closed_field(self):
        self.assertEqual(len(self.projected["sources"]), 39)
        fields = {
            "source_id",
            "title",
            "kind",
            "verification_status",
            "edition_page_status",
        }
        self.assertTrue(all(set(row) == fields for row in self.projected["sources"]))
        self.assertTrue(self.projected["synthetic_only"])
        self.assertIn("待专业复核", self.projected["limits"][0])
        self.assertEqual(
            self.projected["effects"],
            {"model_calls": 0, "user_writes": 0, "network_calls": 0},
        )

    def test_mutating_public_data_does_not_mutate_source(self):
        values = copy.deepcopy(self.values)
        projected = projection.project_course(values, self.hashes)
        projected["lessons"][0]["paragraphs"].append("changed")
        projected["cases"][0]["learning"]["cards"][0]["text"] = "changed"
        self.assertEqual(values, self.values)

    def test_export_is_deterministic_and_manifest_hashes_exact_file(self):
        with tempfile.TemporaryDirectory(dir=WEB / "test-results") as temporary:
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            manifest = projection.export_course(first, self.values, self.hashes)
            projection.export_course(second, self.values, self.hashes)
            body = (first / "course.json").read_bytes()
            self.assertEqual(body, (second / "course.json").read_bytes())
            self.assertEqual(manifest["sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(manifest["bytes"], len(body))
            self.assertEqual(json.loads(body), self.projected)

    def test_invalid_last_lesson_creates_no_output_directory(self):
        values = copy.deepcopy(self.values)
        values[bundle.PREFIX + "lessons/lesson-20.json"]["quiz"][0][
            "correct_option_id"
        ] = "missing"
        with tempfile.TemporaryDirectory(dir=WEB / "test-results") as temporary:
            target = Path(temporary) / "invalid"
            with self.assertRaises(ValueError):
                projection.export_course(target, values, self.hashes)
            self.assertFalse(target.exists())

    def test_existing_export_is_never_replaced(self):
        with tempfile.TemporaryDirectory(dir=WEB / "test-results") as temporary:
            target = Path(temporary)
            sentinel = target / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf8")
            with self.assertRaises(ValueError):
                projection.export_course(target, self.values, self.hashes)
            self.assertEqual(sentinel.read_text(encoding="utf8"), "keep")
            self.assertEqual(list(target.iterdir()), [sentinel])

    def test_export_cannot_escape_web_or_replace_web_root(self):
        for path in (WEB, WEB.parent / "not-allowed-course-output"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                projection.export_course(path, self.values, self.hashes)

    def test_existing_seven_public_assets_remain_byte_identical(self):
        assets = WEB / "public" / "data" / "study"
        before = {str(path): path.read_bytes() for path in assets.rglob("*.json")}
        with tempfile.TemporaryDirectory(dir=WEB / "test-results") as temporary:
            projection.export_course(Path(temporary) / "new", self.values, self.hashes)
        after = {str(path): path.read_bytes() for path in assets.rglob("*.json")}
        self.assertEqual(before, after)
        self.assertGreaterEqual(len(before), 7)

    def test_no_network_is_required_for_projection_or_export(self):
        with mock.patch(
            "socket.socket", side_effect=AssertionError("Network forbidden")
        ):
            with tempfile.TemporaryDirectory(dir=WEB / "test-results") as temporary:
                projection.export_course(
                    Path(temporary) / "offline", self.values, self.hashes
                )


if __name__ == "__main__":
    unittest.main()
