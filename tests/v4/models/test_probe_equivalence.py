"""Bounded capability rehearsal never needs credentials, sockets or auto-start."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from mingjing_core.models.port import AssistantMessage, ToolCall
from mingjing_core.models.quota_types import GuardRejected
from tools import probe_k3_equivalence as probe
from tools.probe_equivalence_cases import CASES, MAX_ATTEMPTS, SCENARIOS


def test_default_mock_is_twenty_wire_requests_without_registry_or_network():
    with (
        patch.object(probe, "ModelRegistry", side_effect=AssertionError("must not read credentials")),
        patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("no socket")),
    ):
        result = probe.run()
    assert result["passed"] is True
    assert (result["model_calls"], result["mock_requests"]) == (0, 20)
    assert len(SCENARIOS) == 9 and len(result["records"]) == 20
    assert {row["model"] for row in result["records"]} == {"k3", "k3-256k"}
    assert result["automatic_next_batch"] is False
    assert result["at"].endswith("+08:00")
    assert all(row["reasoning_present"] for row in result["records"])
    public = json.dumps(result, ensure_ascii=False)
    assert "纯合成私有推理" not in public
    assert "synthetic-signature" not in public
    assert "synthetic-offline-credential" not in public
    assert "tool_arguments" not in public


def test_twenty_attempt_ceiling_fails_before_twenty_first():
    counter = probe.Counter()
    for _ in range(MAX_ATTEMPTS):
        counter.before()
    with pytest.raises(probe.ProbeRejected):
        counter.before()
    assert counter.attempts == MAX_ATTEMPTS


def test_failure_stops_immediately_without_retry_or_next_scenario():
    def fail(handle, case, counter, **kwargs):
        counter.before()
        raise probe.ProbeRejected("synthetic failure")

    with patch.object(probe, "execute_case", side_effect=fail) as calls:
        result = probe.run()
    assert calls.call_count == 1
    assert result["passed"] is False
    assert result["stopped_code"] == "EQUIVALENCE_PROBE_REJECTED"
    assert (result["model_calls"], result["mock_requests"]) == (0, 1)
    assert result["records"] == []


def test_live_without_manual_grant_rejects_before_registry():
    with (
        patch.object(probe, "ModelRegistry", side_effect=AssertionError("no credential access")),
        pytest.raises(probe.ProbeRejected),
    ):
        probe.run(live=True)


def test_bad_grant_never_resolves_models(tmp_path):
    with (
        patch.object(probe, "ModelRegistry", side_effect=AssertionError("no credential access")),
        pytest.raises(GuardRejected) as rejected,
    ):
        probe.run(live=True, grant_path=tmp_path / "absent.json")
    assert rejected.value.kind == "manual_start_required"


def test_cli_defaults_mock_and_refuses_overwrite(tmp_path, capsys):
    path = tmp_path / "result.json"
    assert probe.main(["--output", str(path)]) == 0
    first = path.read_bytes()
    assert json.loads(first)["mode"] == "mock"
    with patch.object(probe, "run", side_effect=AssertionError("must not run again")):
        assert probe.main(["--output", str(path)]) == 2
    assert path.read_bytes() == first
    assert "synthetic-offline-credential" not in capsys.readouterr().out


def test_output_failure_reports_attempts_truthfully(tmp_path, capsys):
    report = {"model_calls": 4, "mock_requests": 0, "passed": False}
    with patch.object(probe, "run", return_value=report), patch.object(Path, "open", side_effect=OSError("full")):
        assert probe.main(["--mode", "live", "--output", str(tmp_path / "report.json")]) == 2
    assert json.loads(capsys.readouterr().out)["model_calls"] == 4


def test_tool_schema_and_nested_arguments_are_checked():
    case = next(row for row in CASES if row.ident == "EQ06")
    good = AssistantMessage(tool_calls=[ToolCall("one", "synthetic_nested", {"payload": {"value": "合成"}})])
    bad = AssistantMessage(tool_calls=[ToolCall("one", "synthetic_nested", {"payload": {"value": "wrong"}})])
    assert probe.check_response(case, good) is True
    assert probe.check_response(case, bad) is False
    assert probe.check_response(case, AssistantMessage(text="合成")) is False
