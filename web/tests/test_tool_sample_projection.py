"""Stdlib-only, offline tests for the public P8 fixture projection.

Fixtures are read from one immutable Git commit. Export tests replace only the
wrapper's Git reader and keep every temporary file below web/test-results.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEB = Path(__file__).resolve().parents[1]
REPOSITORY = WEB.parent
SCRIPTS = WEB / "scripts"
RESULTS = WEB / "test-results"
COMMIT = "6292199d8fdb167d03fe54b07f74060cec59e101"
PREFIX = "docs/v4/contracts/samples/"
FILES = (
    "window-search-ayuan-contract-20261021-27.json",
    "window-search-ayuan-page2.json",
    "window-search-ayuan-empty.json",
    "synastry-ayuan-xiaohe.json",
)
SYN = FILES[-1]
ERROR = "^tool_public_projection_invalid$"


def digest(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf8")).hexdigest()


def at(root: object, path: str) -> object:
    value = root
    for part in path[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def resign(root: dict) -> dict:
    """Repair every integrity seal so negative tests exercise semantic checks."""
    body = {key: root[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
    root["document_id"] = "tool-" + digest(body)
    for alias in root["aliases"]["c"] + root["aliases"]["r"]:
        value_hash = digest(at(root, alias["path"]))
        alias["value_sha256"] = value_hash
        alias["claim_id"] = "claim-" + digest([root["document_id"], alias["path"], value_hash])
    return root


def load_wrapper():
    path = SCRIPTS / "export-tool-samples.py"
    spec = importlib.util.spec_from_file_location("tool_sample_projection_under_test", path)
    module = importlib.util.module_from_spec(spec)
    previous_path, previous_bytecode = sys.path[:], sys.dont_write_bytecode
    try:
        sys.path.insert(0, str(SCRIPTS))
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous_path
        sys.dont_write_bytecode = previous_bytecode
    return module


class ToolSampleProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_wrapper()
        cls.raw = {}
        for filename in FILES:
            result = subprocess.run(
                ["git", "show", f"{COMMIT}:{PREFIX}{filename}"],
                cwd=REPOSITORY,
                check=True,
                capture_output=True,
            )
            cls.raw[filename] = result.stdout

    def root(self, filename=SYN):
        return json.loads(self.raw[filename])

    def project(self, root):
        function = self.module.project_window if root["version"] == "p8-window-search-v1" else None
        return (function or self.module.project_synastry)(root)

    def assert_integrity(self, root):
        body = {key: root[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
        self.assertEqual(root["document_id"], "tool-" + digest(body))
        for alias in root["aliases"]["c"] + root["aliases"]["r"]:
            value_hash = digest(at(root, alias["path"]))
            self.assertEqual(alias["value_sha256"], value_hash)
            claim = digest([root["document_id"], alias["path"], value_hash])
            self.assertEqual(alias["claim_id"], "claim-" + claim)

    def assert_rejected(self, root):
        resign(root)
        self.assert_integrity(root)
        before = copy.deepcopy(root)
        with self.assertRaisesRegex(ValueError, ERROR):
            self.project(root)
        self.assertEqual(root, before)

    def temporary_directory(self):
        RESULTS.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix="tool-projection-", dir=RESULTS)

    def git_reader(self, raw=None):
        values = self.raw if raw is None else raw

        def read(*arguments):
            if arguments == ("rev-parse", self.module.SOURCE_REF):
                return (COMMIT + "\n").encode("ascii")
            for filename in FILES:
                if arguments == ("show", f"{COMMIT}:{PREFIX}{filename}"):
                    return values[filename]
            raise AssertionError(f"Unexpected Git request: {arguments!r}")

        return read

    def test_all_four_fixed_fixtures_project_without_mutating_source(self):
        self.assertEqual(tuple(self.module.FILES), FILES)
        for filename in FILES:
            with self.subTest(filename=filename):
                root = self.root(filename)
                before = copy.deepcopy(root)
                projected = self.project(root)
                self.assertEqual(root, before)
                self.assertEqual(projected["format"], "frontend-tool-sample-v1")
                self.assertEqual(projected["document_id"], root["document_id"])
                expected = "synastry" if filename == SYN else "window_search"
                self.assertEqual(projected["tool"], expected)
                self.assertEqual(
                    projected["effects"],
                    {
                        "model_calls": 0,
                        "writes": 0,
                        "alias_registry": "ephemeral_only",
                    },
                )
                self.assertEqual(len(projected["evidence"]), sum(map(len, root["aliases"].values())))
                for row in projected["evidence"]:
                    self.assertEqual(row["ref"]["document_id"], root["document_id"])
                    if row["kind"] == "rule":
                        for key in ("catalog_id", "school", "school_label"):
                            self.assertIsInstance(row[key], str)
                            self.assertTrue(row[key])
                        self.assertIsInstance(row["source"], dict)
                        self.assertTrue(row["source"]["title"])
                        self.assertLessEqual(set(row["source"]), {"title", "url", "status"})
                        self.assertNotIn("1994-03-12", json.dumps(row["source"]))
                        self.assertNotIn("synthetic-owner", json.dumps(row["source"]))
                self.assertNotIn("scope", projected)
                self.assertNotIn("sources", projected)
                self.assertEqual(resign(copy.deepcopy(root)), root)

    def test_pagination_and_empty_page_keep_the_shared_ranking(self):
        data = [self.module.project_window(self.root(name))["data"] for name in FILES[:3]]
        main, second, empty = data
        self.assertEqual([len(row["candidates"]) for row in data], [7, 3, 0])
        for row in data[1:]:
            self.assertEqual(row["ranking_summary"], main["ranking_summary"])
            self.assertEqual(row["query_sha256"], main["query_sha256"])
        self.assertEqual([row["rank"] for row in second["candidates"]], [4, 5, 6])
        self.assertEqual(
            second["pagination"],
            {
                "total": 7,
                "offset": 3,
                "limit": 3,
                "returned": 3,
                "has_more": True,
                "next_offset": 6,
            },
        )
        self.assertEqual(
            empty["pagination"],
            {
                "total": 7,
                "offset": 7,
                "limit": 3,
                "returned": 0,
                "has_more": False,
                "next_offset": None,
            },
        )
        self.assertEqual(self.module.project_window(self.root(FILES[2]))["evidence"], [])

    def test_resigned_invalid_page_metadata_is_rejected(self):
        for key, value in (("returned", 1), ("has_more", True), ("next_offset", 7), ("offset", -1)):
            with self.subTest(key=key):
                root = self.root(FILES[2])
                root["data"]["pagination"][key] = value
                self.assert_rejected(root)

    def test_tokens_allow_empty_lists_but_reject_empty_or_composite_tokens(self):
        self.assertEqual(self.module.tokens([], "甲乙丙"), [])
        self.assertEqual(self.module.tokens(["甲", "乙"], "甲乙丙"), ["甲", "乙"])
        for values in ([""], ["甲乙"], ["甲", ""], [None], [1]):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, ERROR):
                self.module.tokens(values, "甲乙丙")

    def test_resigned_candidate_tokens_cannot_smuggle_substrings(self):
        for token in ("", "甲乙"):
            with self.subTest(token=token):
                root = self.root()
                row = root["data"]["bazi"]["useful_complement"][3]
                self.assertEqual(row["candidate_stems"], [])
                row["candidate_stems"] = [token]
                self.assert_rejected(root)

    def test_resigned_false_year_branch_combinations_are_rejected(self):
        for kind in ("地支六合", "地支六冲"):
            with self.subTest(kind=kind):
                root = self.root()
                bazi = root["data"]["bazi"]
                self.assertEqual((bazi["pillars_a"]["year"], bazi["pillars_b"]["year"]), ("甲戌", "乙亥"))
                bazi["branch_relations"].append(
                    {
                        "a_pillar": "year",
                        "b_pillar": "year",
                        "a": "甲戌",
                        "b": "乙亥",
                        "kind": kind,
                        "transformation_established": False,
                    }
                )
                self.assert_rejected(root)

    def test_resigned_primary_pillars_must_match_the_same_side_bazi(self):
        for side, wrong in (("a", "乙亥"), ("b", "甲戌")):
            with self.subTest(side=side):
                root = self.root()
                root["data"]["time_basis"][side]["primary"]["pillars"]["year"] = wrong
                self.assert_rejected(root)

    def test_resigned_visible_exposed_stems_must_match_pillars(self):
        for side, wrong in (("a", "乙"), ("b", "甲")):
            with self.subTest(side=side):
                root = self.root()
                view = root["data"]["bazi"][f"visible_{side}"]
                counts = copy.deepcopy(view["element_counts"])
                view["stems"][0] = wrong
                self.assertEqual(view["element_counts"], counts)
                self.assert_rejected(root)

    def test_pointer_decoding_and_bad_pointer_shapes(self):
        sample = {"a/b": {"~name": ["ok"]}}
        self.assertEqual(self.module.pointer(sample, "/a~1b/~0name/0"), "ok")
        for path in (
            "a",
            "/missing",
            "/a~2b",
            "/a~1b/~0name/-1",
            "/a~1b/~0name/00",
            "/a~1b/~0name/1",
            "/a~1b/~0name/-",
        ):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, ERROR):
                self.module.pointer(sample, path)

    def test_bad_document_alias_sha_claim_and_pointer_are_rejected(self):
        root = self.root()
        root["document_id"] = "tool-" + "0" * 64
        with self.assertRaisesRegex(ValueError, ERROR):
            self.project(root)
        for group in ("c", "r"):
            for field, value in (
                ("value_sha256", "0" * 64),
                ("claim_id", "claim-" + "0" * 64),
                ("path", "/data/not~2a~1valid~0pointer"),
            ):
                with self.subTest(group=group, field=field):
                    root = resign(self.root())
                    root["aliases"][group][0][field] = value
                    with self.assertRaisesRegex(ValueError, ERROR):
                        self.project(root)

    def test_non_synthetic_scope_owner_is_rejected_after_resigning(self):
        for filename in (FILES[0], SYN):
            with self.subTest(filename=filename):
                root = self.root(filename)
                root["scope"]["owner_user_id"] = "PRIVATE_REAL_OWNER_SENTINEL"
                self.assert_rejected(root)

    def test_resigned_unreviewed_school_or_source_is_rejected(self):
        cases = ((FILES[0], "window."), (SYN, "synastry.bazi."), (SYN, "synastry.astro."), (SYN, "synastry.ziwei."))
        for filename, prefix in cases:
            for field in ("school", "title", "url"):
                with self.subTest(prefix=prefix, field=field):
                    root = self.root(filename)
                    hit = next(row for row in root["rule_hits"] if row["rule_id"].startswith(prefix))
                    if field == "school":
                        hit["school"] = "SENSITIVE_SCHOOL_SENTINEL"
                    elif isinstance(hit["source"], dict):
                        hit["source"][field] = "SENSITIVE_SOURCE_SENTINEL"
                    else:
                        hit["source"] = "SENSITIVE_SOURCE_SENTINEL"
                    self.assert_rejected(root)

    def test_public_source_edits_cannot_pollute_future_projections(self):
        root = self.root()
        before = copy.deepcopy(root)
        projected = self.project(root)
        rule = next(row for row in projected["evidence"] if row["kind"] == "rule")
        rule["source"]["title"] = "SENSITIVE_MUTATED_PUBLIC_SOURCE_SENTINEL"
        fresh = self.project(root)
        self.assertNotIn("SENSITIVE_MUTATED_PUBLIC_SOURCE_SENTINEL", json.dumps(fresh))
        self.assertEqual(root, before)

    def test_unpublished_birth_time_methods_and_extra_sentinels_are_omitted(self):
        sentinel = "PRIVATE_ASCII_SENTINEL_MUST_NEVER_REACH_PUBLIC_OUTPUT"
        for filename in (FILES[0], SYN):
            with self.subTest(filename=filename):
                root = self.root(filename)
                source = root["data"]
                source["birth"] = {"name": sentinel, "place": sentinel}
                source["extra"] = {"private": sentinel}
                if filename == SYN:
                    source["methods"]["a"]["private"] = sentinel
                    source["time_basis"]["a"]["primary"]["utc"] = sentinel
                    source["time_basis"]["b"]["primary"]["extra"] = sentinel
                else:
                    source["methods"] = {"private": sentinel}
                    source["time_basis"] = {"private": sentinel}
                resign(root)
                before = copy.deepcopy(root)
                projected = self.project(root)
                serialized = json.dumps(projected, ensure_ascii=False)
                self.assertNotIn(sentinel, serialized)
                self.assertNotIn("1994-03-12", serialized)
                self.assertNotIn("1995-08-27", serialized)
                for key in ("birth", "time_basis", "methods", "extra"):
                    self.assertNotIn(key, projected["data"])
                self.assertEqual(root, before)

    def test_export_uses_fixed_bytes_and_writes_only_the_new_staging_directory(self):
        raw_before = dict(self.raw)
        script_before = Path(self.module.__file__).read_bytes()
        with self.temporary_directory() as directory:
            output = Path(directory) / "new-export"
            with mock.patch.object(self.module, "git", side_effect=self.git_reader()) as reader:
                manifest = self.module.export_samples(output)
            self.assertEqual(reader.call_count, 1 + len(FILES))
            self.assertEqual(manifest, json.loads((output / "manifest.json").read_bytes()))
            self.assertEqual(manifest["source_commit"], COMMIT)
            self.assertIs(manifest["synthetic_only"], True)
            self.assertEqual(manifest["model_calls"], 0)
            self.assertEqual({path.name for path in output.iterdir()}, {*FILES, "manifest.json"})
            self.assertEqual({path.name for path in Path(directory).iterdir()}, {"new-export"})
            for entry in manifest["entries"]:
                body = (output / entry["file"]).read_bytes()
                self.assertEqual(entry["sha256"], hashlib.sha256(body).hexdigest())
                provenance = json.loads(body)["provenance"]
                self.assertEqual(provenance["source_commit"], COMMIT)
                self.assertEqual(provenance["source_path"], PREFIX + entry["file"])
                self.assertEqual(provenance["source_sha256"], hashlib.sha256(self.raw[entry["file"]]).hexdigest())
        self.assertEqual(self.raw, raw_before)
        self.assertEqual(Path(self.module.__file__).read_bytes(), script_before)

    def test_export_refuses_to_overwrite_existing_files(self):
        with self.temporary_directory() as directory:
            output = Path(directory) / "existing"
            output.mkdir()
            marker = output / FILES[0]
            marker.write_bytes(b"ORIGINAL_FILE_MUST_STAY_UNCHANGED\n")
            before = marker.read_bytes()
            with (
                mock.patch.object(self.module, "git", side_effect=self.git_reader()),
                self.assertRaises((FileExistsError, ValueError)),
            ):
                self.module.export_samples(output)
            self.assertEqual(marker.read_bytes(), before)
            self.assertEqual({path.name for path in output.iterdir()}, {FILES[0]})

    def test_export_rejects_paths_outside_web_without_creating_them(self):
        with self.temporary_directory() as directory:
            outside = WEB / ".." / (Path(directory).name + "-outside")
            self.assertFalse(outside.resolve().exists())
            with mock.patch.object(self.module, "git", side_effect=self.git_reader()) as reader:
                for output in (outside, WEB):
                    with self.subTest(output=str(output)), self.assertRaisesRegex(ValueError, ERROR):
                        self.module.export_samples(output)
                reader.assert_not_called()
            self.assertFalse(outside.resolve().exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_export_rejects_resigned_invalid_source_before_any_output(self):
        original = self.raw[SYN]
        changed = dict(self.raw)
        root = self.root()
        root["data"]["time_basis"]["a"]["primary"]["pillars"]["year"] = "乙亥"
        changed[SYN] = json.dumps(resign(root), ensure_ascii=False).encode("utf8")
        with self.temporary_directory() as directory:
            output = Path(directory) / "must-not-exist"
            with (
                mock.patch.object(self.module, "git", side_effect=self.git_reader(changed)),
                self.assertRaisesRegex(ValueError, ERROR),
            ):
                self.module.export_samples(output)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(self.raw[SYN], original)


if __name__ == "__main__":
    unittest.main()
