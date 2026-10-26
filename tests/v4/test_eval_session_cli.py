"""Invalid durable-session options stop before credentials, PG, proof or target setup."""

import httpx
import psycopg
import pytest

from mingjing_core.models.quota_runtime import CentralLocation
from tools.eval import live, runner
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.targets import v4_core30
from tools.eval.targets.v4_durable import DurableCore30Target


def test_session_flags_reject_invalid_modes_and_combinations_before_any_io(monkeypatch, tmp_path, record_property):
    session = ["--lifecycle-session", "eval-" + "a" * 32]
    schema = ["--lifecycle-schema", "eval_control_" + "b" * 32]
    scenario = ["--lifecycle-scenario", "T05"]
    flags = session + schema + scenario
    base = ["--mode", "live", "--target", "v4", "--suite", "core30"]
    parsed = runner.parser().parse_args(base + flags)
    assert parsed.lifecycle_session == session[-1] and parsed.lifecycle_schema == schema[-1]
    assert parsed.lifecycle_scenario == scenario[-1]

    def forbidden(*args, **kwargs):
        pytest.fail("INVALID_SESSION_FLAGS_MUST_STOP_BEFORE_CREDENTIALS_PROOF_TARGET_OR_PG")

    for obj, name in (
        (runner.os, "getenv"),
        (runner, "load_scenarios"),
        (v4_core30, "load_core30"),
        (runner, "_run_models"),
        (live, "candidate_gate"),
        (live, "load_core_approval"),
        (CentralLocation, "from_environment"),
        (DurableCore30Target, "__init__"),
        (LifecycleControl, "__init__"),
        (psycopg, "connect"),
        (httpx.Client, "send"),
    ):
        monkeypatch.setattr(obj, name, forbidden)
    cases = [
        base + session,
        base + schema,
        base + scenario,
        flags,
        base + flags + ["--mode", "scripted"],
        base + flags + ["--suite", "default"],
        base + flags + ["--resume"],
        base + flags + ["--validate"],
        base + flags + ["--self-test"],
        base + flags + ["--scenario", "T05"],
        base + flags + ["--scenarios", str(tmp_path)],
        base + flags + ["--lifecycle-scenario", "NOT_A_FIXED_CORE30_ID"],
    ]
    for arguments in cases:
        with pytest.raises(SystemExit) as stopped:
            runner.main(arguments)
        assert stopped.value.code != 0 and "unrecognized arguments" not in str(stopped.value)
    record_property("invalid_session_argument_shapes", len(cases))
    record_property("external_requests", 0)
