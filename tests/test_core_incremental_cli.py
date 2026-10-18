"""Offline CLI boundaries: validation never selects an executable host adapter."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_core_incremental_upgrade import fixture

from tools.core_incremental import main


class IncrementalCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.request = Path(self.temporary.name) / "request.json"
        self.request.write_text(json.dumps(fixture()[0]), encoding="utf-8")
        for name in (
            "subprocess.run",
            "socket.create_connection",
            "psycopg.connect",
            "urllib.request.urlopen",
            "tools.core_incremental_host.NativePort",
            "tools.core_incremental.execute",
        ):
            blocker = patch(name, side_effect=AssertionError("CLI_TEST_EXTERNAL_ESCAPE"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def invoke(self, *arguments: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        argv = ["core_incremental", "--request", str(self.request), *arguments]
        with patch("sys.argv", argv), redirect_stdout(output):
            status = main()
        return status, json.loads(output.getvalue())

    def test_default_only_validates_without_host_adapter_or_effects(self) -> None:
        status, result = self.invoke()
        self.assertEqual(status, 0)
        self.assertTrue(result["validated_request"])
        self.assertEqual(result["database"], "zhiming_core_stage")
        self.assertEqual(len(str(result["controller_sha256"])), 64)
        self.assertEqual(set(Path(self.temporary.name).iterdir()), {self.request})

    def test_apply_without_native_or_approval_rejects_before_adapter(self) -> None:
        for arguments in (("--apply",), ("--apply", "--native")):
            with self.subTest(arguments=arguments):
                status, result = self.invoke(*arguments)
                self.assertEqual(status, 2)
                self.assertEqual(result["code"], "EXPLICIT_HOST_ADAPTER_AND_APPROVAL_REQUIRED")
                self.assertFalse(result["publication"])
        self.assertEqual(set(Path(self.temporary.name).iterdir()), {self.request})

    def test_raw_parsing_error_does_not_echo_input_or_private_exception(self) -> None:
        self.request.write_text("SYNTHETIC_PRIVATE_INPUT_NOT_JSON", encoding="utf-8")
        status, result = self.invoke()
        self.assertEqual(status, 2)
        self.assertEqual(result, {"ok": False, "code": "INCREMENTAL_ACTION_FAILED", "publication": False})


if __name__ == "__main__":
    unittest.main()
