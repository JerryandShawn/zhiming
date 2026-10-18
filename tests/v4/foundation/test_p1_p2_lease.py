"""P1/P2 composition: real disposable PG/service/parser, synthetic HTTP only.

Copy to tests/v4/foundation/ after P1 merge and P2 rebase; p2_repo owns DB cleanup.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from psycopg import sql

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.application import consultation_context
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import FinalAnswer, Intake, ModelUnavailable
from mingjing_core.domain.contracts import BudgetExceeded, EvidenceError, LeaseConflict
from mingjing_core.models.errors import ModelQuotaExhausted
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.repositories.runtime_metadata import program_time
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tests import test_core_repair_recovery as recovery
from tests.test_core_pg_channels import FixtureModel

Row = dict[str, Any]
PRIVATE = "SYNTHETIC_PRIVATE_ECHO"
PUBLIC = json.loads(
    (Path(recovery.__file__).resolve().parents[1] / "tools/eval/fixtures/member_quota_public.json").read_text("utf-8")
)


def _quota(subtype: str) -> httpx.Response:
    envelope = deepcopy(PUBLIC[subtype])
    envelope["error"]["message"] = PRIVATE + " " + envelope["error"]["message"] + " " + PRIVATE
    return httpx.Response(403, json=envelope)


@contextmanager
def _http(respond: Callable[[httpx.Request], httpx.Response]) -> Iterator[None]:
    original = httpx.Client
    with patch(
        "mingjing_core.adapters.model.httpx.Client",
        side_effect=lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    ):
        yield


def _service(repo: PostgresRepository) -> ConsultationService:
    model = ConfiguredModel(key="synthetic-test-only", base="https://synthetic.invalid/v1", model="synthetic")
    return ConsultationService(repo, model=model)


def _purge(service: ConsultationService) -> None:
    with service.repo.transaction() as connection:
        rows = connection.execute(sql.SQL("SELECT id,retry_epoch FROM {}").format(service.repo.table("core_runs")))
        runs = rows.fetchall()
    for run in runs:
        for epoch in range(run["retry_epoch"] + 1):
            service.runtime.purge(run["id"], epoch)


def _rows(repo: PostgresRepository, owner: str, kind: str, run: Row) -> list[Row]:
    return [row for row in repo.list(owner, kind) if row.get("run_id") == run["id"]]


def _charges(repo: PostgresRepository, run: Row) -> int:
    with repo.transaction("alice") as connection:
        row = connection.execute(
            sql.SQL("SELECT count(*) AS count FROM {} WHERE owner=%s AND run_id=%s").format(
                repo.table("core_model_charges")
            ),
            ("alice", run["id"]),
        ).fetchone()
    return row["count"]


def _safe_quota(row: Row, subtype: str) -> None:
    assert row["status"] == "failed"
    assert row["quota_subtype"] == subtype
    assert row["provider_http_status"] == 403
    assert row["provider_error_type"] == "permission_error"
    assert row["provider_message"] == PUBLIC[subtype]["error"]["message"]
    assert len(row["provider_message"]) <= 240
    assert PRIVATE not in json.dumps(row)
    assert "synthetic-test-only" not in json.dumps(row)


@dataclass
class CallProbe:
    repo: PostgresRepository
    service: ConsultationService
    mode: str = "success"
    change: str | None = None
    requests: list[Row] = field(default_factory=list)
    run: Row = field(default_factory=dict)
    fixture: FixtureModel = field(default_factory=FixtureModel)

    def start(self) -> Row:
        queued = self.service.submit(owner="alice", message="合成组合验收", request_id="p1-p2-composition")
        self.run = self.repo.claim_run("alice", queued["id"])
        return self.run

    def call(self, run: Row | None = None) -> Row:
        current = self.run if run is None else run
        clock = consultation_context.program_clock(self.service, "alice", current, persist=False)
        payload = {
            "reference_data": {"message": "合成组合验收", "today": clock.now().date().isoformat()},
            "instruction": "合成日期核对",
            "now": clock.now().isoformat(),
        }
        return self.service._call(
            "alice", current, current["lease_token"], "intake", payload, Intake, program_at=clock.now().isoformat()
        )

    def mutate(self) -> None:
        assert self.change is not None
        if self.change == "cancel":
            self.repo.fail_run("alice", self.run["id"], "合成取消", self.run["lease_token"], status="cancelled")
            return
        clauses = {
            "expiry": "lease_until=now()-interval '1 second'",
            "token": "lease_token='synthetic-replacement'",
            "epoch": "retry_epoch=retry_epoch+1",
        }
        with self.repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET {} WHERE owner=%s AND id=%s").format(
                    self.repo.table("core_runs"), sql.SQL(clauses[self.change])
                ),
                ("alice", self.run["id"]),
            )

    def respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        payload = json.loads(body["messages"][0]["content"][0]["text"])
        self.requests.append(deepcopy(payload))
        if self.change:
            self.mutate()
        if self.mode == "network":
            raise httpx.ReadTimeout(PRIVATE, request=request)
        if self.mode.startswith("quota_"):
            return _quota(self.mode)
        result = self.fixture.generate(
            system="合成", payload=payload, schema=body["tools"][0]["input_schema"], purpose="intake"
        )
        return httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "name": "submit", "input": result["output"]}],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 11, "output_tokens": 7},
            },
        )


@pytest.fixture
def combo_clock() -> Iterator[FrozenClock]:
    original = get_clock()
    frozen = FrozenClock(datetime.fromisoformat("2030-01-02T10:30:00+08:00"))
    set_clock(frozen)
    try:
        yield frozen
    finally:
        set_clock(original)


@pytest.fixture
def call_probe(p2_repo: PostgresRepository, combo_clock: FrozenClock) -> Iterator[CallProbe]:
    probe = CallProbe(p2_repo, _service(p2_repo))
    try:
        with _http(probe.respond):
            yield probe
    finally:
        _purge(probe.service)


@pytest.fixture
def repair_probe(p2_repo: PostgresRepository, combo_clock: FrozenClock) -> Iterator[recovery.CoreRepairRecovery]:
    # Reuse response/retry helpers without setUp: the inherited p2_repo owns the schema.
    probe = recovery.CoreRepairRecovery("runTest")
    probe.repo, probe.service = p2_repo, _service(p2_repo)
    p2_repo.ensure_owner("fictional")
    probe.requests, probe.repairs, probe.behavior, probe.decision = [], [], ["network", "success"], False

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        payload = json.loads(body["messages"][0]["content"][0]["text"])
        if "errors" in payload and probe.behavior[0].startswith("quota_"):
            probe.requests.append("repair")
            probe.repairs.append(deepcopy(payload))
            return _quota(probe.behavior[0])
        return probe.respond(request)

    try:
        with _http(respond):
            yield probe
    finally:
        _purge(probe.service)


@pytest.mark.parametrize("subtype", ["quota_5h", "quota_weekly"])
def test_quota_diagnostic_and_program_time_share_accepted_lease(call_probe: CallProbe, subtype: str) -> None:
    run = call_probe.start()
    call_probe.mode = subtype
    with pytest.raises(ModelQuotaExhausted) as caught:
        call_probe.call()
    diagnostics = _rows(call_probe.repo, "alice", "model_call", run)
    assert len(diagnostics) == len(call_probe.requests) == 1
    _safe_quota(diagnostics[0], subtype)
    assert PRIVATE not in str(caught.value)
    assert call_probe.service._record("alice", run["id"], "program_time") == {
        "at": get_clock().now().astimezone(UTC).isoformat()
    }
    assert call_probe.service._record("alice", run["id"], "model:intake") is None
    assert call_probe.repo.fetch_run("alice", run["id"])["calls"] == 1


def test_network_retry_success_and_cache_preserve_clock(call_probe: CallProbe, combo_clock: FrozenClock) -> None:
    run = call_probe.start()
    call_probe.mode = "network"
    with pytest.raises(ModelUnavailable):
        call_probe.call()
    first = call_probe.service._record("alice", run["id"], "program_time")
    failed = _rows(call_probe.repo, "alice", "model_call", run)[0]
    assert failed["reason"] == "network" and not failed["usage_known"]
    assert PRIVATE not in json.dumps(failed)
    combo_clock.advance(timedelta(days=1, microseconds=1))
    call_probe.mode = "success"
    result = call_probe.call()
    assert call_probe.requests[0] == call_probe.requests[1]
    assert call_probe.call() == result
    assert len(call_probe.requests) == call_probe.repo.fetch_run("alice", run["id"])["calls"] == 2
    rows = _rows(call_probe.repo, "alice", "model_call", run)
    succeeded = next(row for row in rows if row["status"] == "succeeded")
    assert succeeded["usage"] == {"input_tokens": 11, "output_tokens": 7}
    assert call_probe.service._record("alice", run["id"], "program_time") == first


@pytest.mark.parametrize("mode", ["success", "quota_5h", "network"])
def test_diagnostic_and_real_metadata_roll_back_together(call_probe: CallProbe, mode: str) -> None:
    run = call_probe.start()
    call_probe.mode = mode
    before = call_probe.repo.get_revision("alice")
    writes: list[str] = []

    def abort(repo: PostgresRepository, owner: str, current: Row, at: str, *, write: bool = True) -> str:
        if not write:
            return program_time(repo, owner, current, at, write=False)
        diagnostic = _rows(repo, owner, "model_call", current)
        assert len(diagnostic) == 1
        if mode.startswith("quota_"):
            _safe_quota(diagnostic[0], mode)
        revision = repo.get_revision(owner)
        writes.append(program_time(repo, owner, current, at))
        assert repo.get_revision(owner) == revision
        assert len(_rows(repo, owner, "runtime_step", current)) == 1
        raise EvidenceError("合成事务回滚")

    with patch.object(consultation_context, "program_time", abort), pytest.raises(EvidenceError, match="合成事务回滚"):
        call_probe.call()
    assert writes == [get_clock().now().astimezone(UTC).isoformat()]
    assert _rows(call_probe.repo, "alice", "model_call", run) == []
    assert _rows(call_probe.repo, "alice", "runtime_step", run) == []
    assert call_probe.repo.get_revision("alice") == before
    assert call_probe.repo.fetch_run("alice", run["id"])["calls"] == len(call_probe.requests) == 1
    assert _charges(call_probe.repo, run) == 1


@pytest.mark.parametrize("change", ["cancel", "expiry", "token", "epoch"])
@pytest.mark.parametrize("mode", ["success", "quota_5h", "network"])
def test_late_result_cannot_write_after_lease_or_epoch_changes(call_probe: CallProbe, change: str, mode: str) -> None:
    run = call_probe.start()
    before = call_probe.repo.get_revision("alice")
    call_probe.mode, call_probe.change = mode, change
    with pytest.raises(EvidenceError if change == "epoch" else LeaseConflict):
        call_probe.call()
    assert len(call_probe.requests) == call_probe.repo.fetch_run("alice", run["id"])["calls"] == 1
    assert _rows(call_probe.repo, "alice", "model_call", run) == []
    assert _rows(call_probe.repo, "alice", "runtime_step", run) == []
    assert call_probe.repo.get_revision("alice") == before
    assert _charges(call_probe.repo, run) == 1


@pytest.mark.parametrize("field,value", [("lease_token", "synthetic-wrong-token"), ("retry_epoch", 1)])
def test_invalid_preflight_has_no_call_or_metadata(call_probe: CallProbe, field: str, value: str | int) -> None:
    run = call_probe.start()
    changed = dict(run, **{field: value})
    before = call_probe.repo.get_revision("alice")
    with pytest.raises((LeaseConflict, EvidenceError)):
        call_probe.call(changed)
    assert call_probe.requests == []
    assert call_probe.repo.fetch_run("alice", run["id"])["calls"] == 0
    assert _rows(call_probe.repo, "alice", "runtime_step", run) == []
    assert call_probe.repo.get_revision("alice") == before
    assert _charges(call_probe.repo, run) == 0


def test_metadata_replay_does_not_increment_owner_revision(call_probe: CallProbe, combo_clock: FrozenClock) -> None:
    run = call_probe.start()
    before = call_probe.repo.get_revision("alice")
    first = consultation_context.program_clock(call_probe.service, "alice", run).now()
    combo_clock.advance(timedelta(days=1))
    assert consultation_context.program_clock(call_probe.service, "alice", run).now() == first
    assert call_probe.repo.get_revision("alice") == before
    assert call_probe.repo.fetch_run("alice", run["id"])["calls"] == 0
    assert len(_rows(call_probe.repo, "alice", "runtime_step", run)) == 1
    call_probe.repo.put("alice", "note", "semantic-control", {"content": "合成普通写入"}, expected_revision=0)
    assert call_probe.repo.get_revision("alice") > before


def test_full_repair_retry_keeps_program_time_payload_and_identity(
    repair_probe: recovery.CoreRepairRecovery, combo_clock: FrozenClock
) -> None:
    with pytest.raises(ModelUnavailable):
        repair_probe.consult()
    failed = repair_probe.current()
    first = repair_probe.service._record("fictional", failed["id"], "program_time")
    assert failed["calls"] == 3
    combo_clock.advance(timedelta(days=1, microseconds=1))
    result = repair_probe.retry(failed)
    current = repair_probe.current()
    rows = repair_probe.repair_diagnostics(current)
    assert result["validation"]["valid"]
    assert current["status"] == "succeeded" and current["retry_epoch"] == 0
    assert current["calls"] == len(repair_probe.requests) == 4
    assert repair_probe.repairs[0] == repair_probe.repairs[1]
    assert len({row["repair_identity"] for row in rows}) == 1
    assert [row["repair_outcome"] for row in rows] == ["transient_failure", "succeeded"]
    assert [row["repair_epoch"] for row in rows] == [0, 0]
    assert rows[1]["usage"] == {"input_tokens": 11, "output_tokens": 7}
    assert "PRIVATE_SYNTHETIC_PROVIDER_BODY" not in json.dumps(rows)
    assert repair_probe.service._record("fictional", current["id"], "program_time") == first
    assert repair_probe.consult() == result
    assert len(repair_probe.requests) == 4


@pytest.mark.parametrize("subtype", ["quota_5h", "quota_weekly"])
def test_quota_cannot_reopen_repair_round(repair_probe: recovery.CoreRepairRecovery, subtype: str) -> None:
    repair_probe.behavior = [subtype]
    with pytest.raises(ModelQuotaExhausted):
        repair_probe.consult()
    failed = repair_probe.current()
    row = repair_probe.repair_diagnostics(failed)[0]
    _safe_quota(row, subtype)
    assert row["repair_outcome"] == "terminal_failure" and row["repair_epoch"] == 0
    assert repair_probe.service._record("fictional", failed["id"], "program_time") is not None
    with pytest.raises(BudgetExceeded):
        repair_probe.retry(failed)
    assert repair_probe.current()["calls"] == len(repair_probe.requests) == 3
    assert len(repair_probe.repairs) == 1


def test_new_epoch_cannot_reuse_old_repair_identity(
    repair_probe: recovery.CoreRepairRecovery, combo_clock: FrozenClock
) -> None:
    with pytest.raises(ModelUnavailable):
        repair_probe.consult()
    failed = repair_probe.current()
    old = repair_probe.service._record("fictional", failed["id"], "program_time")
    with repair_probe.repo.transaction("fictional") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET status='stale' WHERE owner=%s AND id=%s").format(
                repair_probe.repo.table("core_runs")
            ),
            ("fictional", failed["id"]),
        )
    combo_clock.advance(timedelta(days=1))
    prepared = repair_probe.repo.prepare_retry("fictional", failed["id"])
    assert prepared["run"]["retry_epoch"] == 1
    current = repair_probe.repo.claim_run("fictional", failed["id"])
    before = repair_probe.repo.get_revision("fictional")
    assert consultation_context.program_clock(repair_probe.service, "fictional", current).now() == combo_clock.now()
    assert repair_probe.repo.get_revision("fictional") == before
    assert repair_probe.service._record("fictional", current["id"], "program_time") != old
    with pytest.raises(BudgetExceeded):
        repair_probe.service._call(
            "fictional",
            current,
            current["lease_token"],
            "repair",
            deepcopy(repair_probe.repairs[0]),
            FinalAnswer,
            repair=True,
        )
    assert repair_probe.current()["calls"] == len(repair_probe.requests) == 3
    assert len(repair_probe.repair_diagnostics(current)) == 1
