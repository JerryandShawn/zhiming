"""X02 executes actual finite HTTP faults without inventing a fallback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from psycopg import sql

from tools.eval.contracts import scenario_contract_hash
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenario
from tools.eval.targets import v4_target
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_http_faults import MODEL, HttpFaultPort
from tools.eval.targets.v4_live import V4LiveTarget
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture

SCENARIOS = Path(__file__).resolve().parents[3] / "tools/eval/scenarios"


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


def test_x02_actual_503_503_200_keeps_one_primary_and_original_fallback_assertion_red(
    target: V4Target,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    original = load_scenario(SCENARIOS / "X02.yaml")
    scenario = execution_overlay(original)
    assert scenario_contract_hash(scenario) == scenario_contract_hash(original)
    _reject_before_io(target, scenario.seed.model_dump(mode="json"), monkeypatch)
    result = evaluate_scenario(scenario, target, target_name="v4")
    assert result["status"] == "failed" and result["failed_assertions"] == ["turn[1].db[1]", "turn[1].events"]
    assert result["previews"] == [scenario.scripted[0].model[0].text]
    assert result["target_model_calls"] == result["model_calls"] == 3
    assert isinstance(target.port, HttpFaultPort)
    proof = target.case_evidence()["http_faults"]
    assert proof["mock_http_requests"] == proof["adapter_http_requests"] == 3
    assert proof["logical_model_steps"] == proof["success_actions_consumed"] == 1
    assert proof["pending_actions"] == proof["external_provider_requests"] == 0
    assert [row["http_status"] for row in proof["attempts"]] == [503, 503, 200]
    assert [row["pending_actions"] for row in proof["attempts"]] == [1, 1, 1]
    assert {row["model"] for row in proof["attempts"]} == {MODEL} and proof["selected_models"] == [MODEL]
    assert len({row["request_sha256"] for row in proof["attempts"]}) == 1
    assert [row["kind"] for row in proof["classified_errors"]] == ["unavailable", "unavailable"]
    assert all(row["http_status"] == 503 and row["max_attempts"] == 4 for row in proof["classified_errors"])
    assert len(proof["retry_delays_seconds"]) == 2
    assert 1 <= proof["retry_delays_seconds"][0] <= 1.2 and 3 <= proof["retry_delays_seconds"][1] <= 3.2
    assert [row["name"] for row in target.semantic] == ["model.error", "model.error"]
    _assert_persisted(target)
    record_property("actual_mock_http_statuses", "503/503/200")
    record_property("logical_model_steps", 1)
    record_property("external_provider_requests", 0)
    record_property("original_x02", "failed: fallback DB assertion and event; gold unchanged")


def _assert_persisted(target: V4Target) -> None:
    repo = target.repo
    assert repo is not None and len(target.run_ids) == 1
    run = repo.fetch_run(target.owner, target.run_ids[0])
    assert run["status"] == "succeeded" and run["runtime"] == "v4"
    assert run["result"]["text"] and run["result"]["schema"] == "core4.0"
    with repo.transaction(target.owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT kind,status,output FROM {} WHERE owner=%s AND run_id=%s AND kind='model' ORDER BY seq"
            ).format(repo.table("core_run_steps")),
            (target.owner, run["id"]),
        ).fetchall()
    assert len(rows) == 1 and rows[0]["kind"] == "model" and rows[0]["status"] == "completed"
    assert rows[0]["output"]["assistant"]["model"] == MODEL
    assert target.inspect_db()["run_meta"].get("fallbacks", []) == []


def _reject_before_io(target: V4Target, seed: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args, **kwargs):
        raise AssertionError("Invalid fault controls reached I/O")

    with monkeypatch.context() as boundary:
        boundary.setattr(v4_target, "verify_local_postgres", reject)
        boundary.setattr("tools.eval.targets.v4_http_faults.TemporaryDirectory", reject)
        for errors in ([], [500], [503] * 4, [True], "503", None):
            invalid = seed | {"controls": {"primary_errors": errors}}
            with pytest.raises(ValueError, match="有限503"):
                target.reset(invalid)
            assert target.repo is None
        for conflict in ("provider_failures", "crash_after", "revoke_after_context"):
            invalid = seed | {"controls": {"primary_errors": [503], conflict: True}}
            with pytest.raises(ValueError, match="有限503"):
                target.reset(invalid)
        assert target.repo is None
        protocol_target = V4Target(dsn=target.dsn, protocol="openai_compat")
        live_target = V4LiveTarget(dsn=target.dsn, model="unverified-candidate", environment={})
        for incompatible in (protocol_target, live_target):
            with pytest.raises(ValueError, match="有限503"):
                incompatible.reset(seed)
            assert incompatible.repo is None
