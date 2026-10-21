"""Independent child processes reject optimized measurement before any Core import; no workload is run."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROBE = r"""
import json, sys
try:
    import tools.mod_week.benchmark_reflection_projection_RPF01 as b
except RuntimeError as error:
    result = {"status": "guarded", "optimize": sys.flags.optimize,
              "message": str(error), "core_loaded": any(n.startswith("mingjing_core") for n in sys.modules)}
else:
    b.isolate_process()
    original = b.semantic_capture
    values = iter((("synthetic-baseline",), ("synthetic-mismatch",)))
    b.semantic_capture = lambda fixture: next(values)
    try:
        try:
            b.assert_parity(b"", ())
        except AssertionError:
            status = "semantic_mismatch_rejected"
        else:
            status = "incorrectly_accepted"
    finally:
        b.semantic_capture = original
    result = {"status": status, "optimize": sys.flags.optimize,
              "restored": b.semantic_capture is original and all(m.dataclass_json is b.ORACLE for m in b.MODULES)}
print(json.dumps(result))
"""


@pytest.mark.parametrize("flags", [(), ("-O",), ("-OO",)])
def test_measurement_mode_is_explicit_before_import_or_semantic_comparison(flags: tuple[str, ...]) -> None:
    env = dict(os.environ)
    for key in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        env[key] = ""
    env["LANGCHAIN_TRACING_V2"] = env["LANGSMITH_TRACING"] = "false"
    process = subprocess.run(
        [sys.executable, "-E", "-B", *flags, "-c", PROBE],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=True,
    )
    result = json.loads(process.stdout)
    assert not process.stderr
    if flags:
        assert result["status"] == "guarded" and result["optimize"] in {1, 2} and not result["core_loaded"]
        assert result["message"] == "该离线测量工具需要标准解释器模式，请关闭优化模式"
    else:
        assert result["status"] == "semantic_mismatch_rejected" and result["optimize"] == 0 and result["restored"]
