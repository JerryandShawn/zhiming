"""The synthetic b9 package must stay fixed as newer branches acquire migrations."""

from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace

import test_core_incremental_native as native

from tools.core_incremental_contracts import MIGRATIONS, UpgradeRejected
from tools.core_incremental_files import file_sha, private_write


class NativeFixedCandidateFixtureTests(unittest.TestCase):
    def fixture(self) -> native.NativeAdapterTests:
        case = native.NativeAdapterTests("test_pinned_release_rejects_changed_source_and_extra_file")
        self.addCleanup(case.doCleanups)
        case.setUp()
        return case

    def reapprove_manifest(self, case: native.NativeAdapterTests, member: str) -> None:
        root = case.files.path(case.request.release)
        path = root / "__release_manifest__.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["files"][member] = {"sha256": file_sha(root / member)}
        private_write(path, json.dumps(document).encode(), replace=True)
        # Only this injected synthetic filesystem can override the manifest approval.
        case.request = replace(case.request, manifest_sha256=file_sha(path))
        case.files.approved_manifest = case.request.manifest_sha256

    def test_exact_seven_migration_fixture_keeps_independent_checksum_guard(self) -> None:
        case = self.fixture()
        root = case.files.path(case.request.release)
        self.assertTrue(case.files.release(case.request))
        paths = sorted((root / "mingjing_core/repositories/migrations").glob("*.sql"))
        actual = {
            str(int(path.name[:4])): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in paths
        }
        self.assertEqual(actual, MIGRATIONS)
        source = paths[-1]
        source.write_bytes(source.read_bytes() + b"\n-- synthetic changed migration\n")
        self.reapprove_manifest(case, source.relative_to(root).as_posix())
        with self.assertRaisesRegex(UpgradeRejected, "PACKAGE_MIGRATIONS"):
            case.files.release(case.request)
        self.assertEqual(case.commands.calls, [])
        self.assertFalse(case.port.gate.exists())

    def test_rehashed_manifest_cannot_admit_p1b_eighth_migration_into_b9(self) -> None:
        case = self.fixture()
        root = case.files.path(case.request.release)
        member = "mingjing_core/repositories/migrations/0008_model_usage.sql"
        private_write(root / member, (native.REPO / member).read_bytes())
        self.reapprove_manifest(case, member)
        with self.assertRaisesRegex(UpgradeRejected, "PACKAGE_MIGRATIONS"):
            case.files.release(case.request)
        self.assertEqual(case.commands.calls, [])
        self.assertFalse(case.port.gate.exists())


if __name__ == "__main__":
    unittest.main()
