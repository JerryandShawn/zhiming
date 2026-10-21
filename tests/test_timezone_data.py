"""Timezone-only regressions; no chart dependencies, databases or external calls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zoneinfo
from datetime import datetime
from importlib import resources
from pathlib import Path
from unittest.mock import patch

from tools import verify_timezone_data as verifier

REPO = Path(__file__).resolve().parents[1]


class TimezoneDataTests(unittest.TestCase):
    def test_fixed_package_boundaries_and_digest(self) -> None:
        report = verifier.verify(REPO)
        self.assertEqual(report["sha256"], verifier.EXPECTED_DIGEST)
        snapshot = report["snapshot"]
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["tzpath"], [])
        self.assertEqual(len(snapshot["cases"]), 21)

    def test_lock_pin_hash_and_duplicate_rejections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for name in ("requirements-core.lock", "requirements-charts.lock", "tools/timezone/tzdata.lock"):
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REPO / name).read_bytes())
            for name, replacement in (
                ("requirements-charts.lock", "tzdata==2026.4\n"),
                ("requirements-charts.lock", "tzdata==2026.5\ntzdata==2026.5\n"),
                ("tools/timezone/tzdata.lock", "tzdata==2026.5\n"),
                ("requirements-core.lock", "tzdata==2026.5\n"),
            ):
                with self.subTest(name=name, replacement=replacement):
                    target = repo / name
                    original = target.read_bytes()
                    target.write_text(replacement, encoding="utf-8")
                    with self.assertRaises(verifier.TimezoneVerificationError):
                        verifier.verify_locks(repo)
                    target.write_bytes(original)

    def test_package_versions_and_resource_hashes_are_checked(self) -> None:
        for name, value in (("__version__", "2026.4"), ("IANA_VERSION", "2026d")):
            with (
                self.subTest(name=name),
                patch.object(verifier.tzdata, name, value),
                self.assertRaises(verifier.TimezoneVerificationError),
            ):
                verifier.snapshot()
        with (
            patch.object(verifier.metadata, "version", return_value="2026.4"),
            self.assertRaises(verifier.TimezoneVerificationError),
        ):
            verifier.snapshot()
        with (
            patch.dict(verifier.ZONE_HASHES, {"Asia/Shanghai": "0" * 64}),
            self.assertRaises(verifier.TimezoneVerificationError),
        ):
            verifier.snapshot()

    def test_system_path_and_preexisting_cache_cannot_mask_package_rules(self) -> None:
        previous = zoneinfo.TZPATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                fake = Path(directory) / "Asia" / "Shanghai"
                fake.parent.mkdir()
                fake.write_bytes(resources.files("tzdata.zoneinfo").joinpath("UTC").read_bytes())
                zoneinfo.reset_tzpath((directory,))
                zoneinfo.ZoneInfo.clear_cache()
                instant = datetime.fromisoformat("2026-10-17T00:00:00+00:00")
                self.assertEqual(instant.astimezone(zoneinfo.ZoneInfo("Asia/Shanghai")).hour, 0)
                report = verifier.verify(REPO)
                self.assertEqual(report["sha256"], verifier.EXPECTED_DIGEST)
                self.assertEqual(zoneinfo.TZPATH, (directory,))
        finally:
            zoneinfo.reset_tzpath(previous)
            zoneinfo.ZoneInfo.clear_cache()

    def test_fresh_cli_disables_ambient_system_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            environment = os.environ.copy()
            environment["PYTHONTZPATH"] = directory
            result = subprocess.run(
                [sys.executable, str(REPO / "tools/verify_timezone_data.py"), "--output", str(output)],
                cwd=REPO,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["sha256"], verifier.EXPECTED_DIGEST)
            self.assertEqual(report["snapshot"]["tzpath"], [])


if __name__ == "__main__":
    unittest.main()
