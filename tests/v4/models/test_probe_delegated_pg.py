"""Synthetic provider wire against real isolated central/control PostgreSQL."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import psycopg
import pytest
from psycopg import sql

from mingjing_core.models.quota_delegated import approval_from_gate
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock
from tools import probe_equivalence_delegated as delegated
from tools import probe_k3_equivalence as original
from tools.probe_equivalence_cases import SCENARIOS
from tools.probe_equivalence_control import ProbeControl, ProbeControlError
from tools.probe_equivalence_mock import mock_transport
from tools.probe_equivalence_proof import approval_from_equivalence, load_core_approval, proof_report

from .test_delegated_policy import CANDIDATE, NOW, gate
from .test_quota_guard_pg import configure_central

SOURCE = "b" * 64


@pytest.fixture(name="fixture")
def fixture_setup(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    def deny(*args: Any, **kwargs: Any) -> None:
        pytest.fail("real external transport forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)
    central = configure_central(p2_repo, monkeypatch)
    guard = QuotaGuard(**central, clock=FrozenClock(NOW))
    controls = []

    def make_control(initialize: bool = True) -> ProbeControl:
        control = ProbeControl(p2_repo.dsn, "probe_test_" + uuid.uuid4().hex)
        controls.append(control)
        if initialize:
            control.initialize()
        return control

    base = original.configuration(False, None)[0]
    yield SimpleNamespace(central=central, guard=guard, make_control=make_control, base=base)
    with psycopg.connect(p2_repo.dsn, autocommit=True) as connection:
        for control in controls:
            assert control.schema.startswith("probe_test_")
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(control.schema)))


def session(fixture: Any, candidate: str = CANDIDATE) -> DelegatedSession:
    value = gate()
    value["candidate_commit"] = candidate
    for name in ("p3", "core", "date_checks"):
        value[name]["candidate_commit"] = candidate
    approved = approval_from_gate(value, candidate, fixture.guard.clock.now())
    return DelegatedSession(fixture.guard, approved, phase="equivalence", scenario_ids=SCENARIOS)


def substitute_live_boundary(monkeypatch: pytest.MonkeyPatch, *, fail_check: bool = False) -> None:
    # Exercise the production branch with only HTTP replaced. No result is
    # published as actual model quality; the control schema is destroyed afterward.
    def make(base: Any, case: Any, guard: Any, transport_factory: Any) -> Any:
        transport = mock_transport(case, [])

        def respond(request: httpx.Request) -> httpx.Response:
            response = transport.handle_request(request)
            if fail_check and case.ident == "EQ01" and json.loads(request.content)["model"] == "k3-256k":
                return httpx.Response(
                    200, content=response.content.replace('"text": "合成"'.encode(), '"text": "不同"'.encode())
                )
            return response

        return base.adapter(max_retries=0, guard=guard, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(delegated, "make_adapter", make)


def test_initialization_is_explicit_and_does_not_resolve_or_call_models(
    fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = fixture.make_control(False)
    run = session(fixture)
    with pytest.raises(ProbeControlError):
        delegated.run_delegated(
            fixture.base,
            run,
            control,
            source_sha256=SOURCE,
            transport_factory=lambda case: pytest.fail("no request without DDL"),
        )
    monkeypatch.setenv("PROBE_TEST_DSN", control.dsn)
    monkeypatch.setattr(delegated, "ModelRegistry", lambda: pytest.fail("initialization is not a probe"))
    args = SimpleNamespace(
        control_dsn_env="PROBE_TEST_DSN", control_schema=control.schema, mode="init-control", init_control_schema=False
    )
    with pytest.raises(ProbeControlError):
        delegated.delegated_cli(args)
    args.init_control_schema = True
    assert delegated.delegated_cli(args) == 0
    assert control.physical(fixture.guard) == []
    with pytest.raises(ProbeControlError):
        ProbeControl(control.dsn, fixture.guard.store.schema)


@pytest.mark.parametrize("dsn", ["postgresql://x@remote.invalid/eval", "postgresql://x@127.0.0.1/production"])
def test_control_store_rejects_nonlocal_or_production_before_connection(dsn: str) -> None:
    with pytest.raises(ValueError):
        ProbeControl(dsn, "probe_only")


def test_full_mock_proof_is_twenty_checked_rows_but_never_production_approval(fixture: Any) -> None:
    control = fixture.make_control()
    run = session(fixture)
    proof = delegated.run_delegated(
        fixture.base, run, control, source_sha256=SOURCE, transport_factory=lambda case: mock_transport(case, [])
    )
    assert proof["complete"] and proof["equivalent"] and proof["selected_model"] == "k3-256k"
    assert proof["model_calls"] == len(proof["records"]) == len(proof["attempt_ids"]) == 20
    assert {row["scenario"] for row in proof["records"]} == set(SCENARIOS)
    assert {row["model"] for row in proof["records"]} == {"k3", "k3-256k"}
    with pytest.raises(GuardRejected):
        approval_from_equivalence(fixture.guard, run.approval, proof, control=control, source_sha256=SOURCE)
    public = json.dumps(proof, ensure_ascii=False)
    assert all(
        value not in public for value in ("纯合成私有推理", "synthetic-signature", "synthetic-offline-credential")
    )
    repeated = delegated.run_delegated(
        fixture.base,
        session(fixture),
        control,
        source_sha256=SOURCE,
        transport_factory=lambda case: pytest.fail("complete proof does not replay"),
    )
    assert repeated == proof


def test_live_branch_uses_pg_checks_and_rejects_source_account_file_and_ledger_tampering(
    fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    substitute_live_boundary(monkeypatch)
    control, run = fixture.make_control(), session(fixture)
    proof = delegated.run_delegated(fixture.base, run, control, source_sha256=SOURCE)
    approved = approval_from_equivalence(fixture.guard, run.approval, proof, control=control, source_sha256=SOURCE)
    assert approved.equivalent is True
    path = tmp_path / "synthetic-unit-fixture-proof.json"
    path.write_text(json.dumps(proof), encoding="utf-8")
    assert load_core_approval(fixture.guard, run.approval, path, control=control, source_sha256=SOURCE).equivalent
    for changed in ({"equivalent": False}, {"complete": False}, {"account_id": "other"}, {"attempt_ids": []}):
        forged = {**proof, **changed}
        with pytest.raises(GuardRejected):
            approval_from_equivalence(fixture.guard, run.approval, forged, control=control, source_sha256=SOURCE)
    with pytest.raises(GuardRejected):
        approval_from_equivalence(fixture.guard, run.approval, proof, control=control, source_sha256="c" * 64)
    wrong_control = fixture.make_control()
    with pytest.raises(ProbeControlError):
        approval_from_equivalence(fixture.guard, run.approval, proof, control=wrong_control, source_sha256=SOURCE)
    with fixture.guard.store.connect() as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET model='different' WHERE attempt_id=%s").format(
                fixture.guard.store.table("core_model_usage")
            ),
            (proof["attempt_ids"][0],),
        )
    with pytest.raises(ProbeControlError):
        proof_report(control, fixture.guard, proof["evaluation_session_id"])


def test_complete_non_equivalence_can_select_k3_but_only_after_all_twenty_steps(
    fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    substitute_live_boundary(monkeypatch, fail_check=True)
    control, run = fixture.make_control(), session(fixture)
    proof = delegated.run_delegated(fixture.base, run, control, source_sha256=SOURCE)
    assert proof["complete"] and proof["equivalent"] is False and proof["model_calls"] == 20
    assert proof["selected_model"] == "k3" and sum(not row["passed"] for row in proof["records"]) == 1
    assert (
        approval_from_equivalence(fixture.guard, run.approval, proof, control=control, source_sha256=SOURCE).equivalent
        is False
    )


@pytest.mark.parametrize(
    "message,reset,kind",
    [
        ("5-hour usage limit", "18000", "quota_5h"),
        ("5-hour usage limit", None, "quota_5h"),
        ("Access terminated", None, "access_terminated"),
    ],
)
def test_provider_stop_preserves_checkpoint_and_never_turns_incomplete_into_fallback(
    fixture: Any,
    message: str,
    reset: str | None,
    kind: str,
) -> None:
    control, run = fixture.make_control(), session(fixture)
    sent = []

    def transport(case: Any) -> httpx.MockTransport:
        def respond(request: httpx.Request) -> httpx.Response:
            sent.append(1)
            return httpx.Response(
                429,
                headers={"Retry-After": reset} if reset else {},
                json={"error": {"type": "permission_error", "message": message}},
            )

        return httpx.MockTransport(respond)

    proof = delegated.run_delegated(fixture.base, run, control, source_sha256=SOURCE, transport_factory=transport)
    assert proof["model_calls"] == 1 and proof["complete"] is False and proof["equivalent"] is None
    assert proof["stop_kind"] == kind and proof["selected_model"] is None and not proof["budget_sufficient"]
    assert bool(proof["resume_at"]) == bool(reset)
    fixture.guard.clock.advance(timedelta(hours=6))
    resumed = delegated.run_delegated(
        fixture.base, session(fixture), control, source_sha256=SOURCE, transport_factory=transport, resume=True
    )
    assert sent == [1] and not resumed["complete"] and fixture.guard.status()["stop_kind"] == kind
    with pytest.raises(GuardRejected):
        approval_from_equivalence(fixture.guard, run.approval, resumed, control=control, source_sha256=SOURCE)
    with pytest.raises(ProbeControlError):
        delegated.run_delegated(
            fixture.base,
            session(fixture, "c" * 40),
            control,
            source_sha256="d" * 64,
            transport_factory=transport,
            resume=True,
        )
    other_control = fixture.make_control()
    other = delegated.run_delegated(
        fixture.base, session(fixture), other_control, source_sha256=SOURCE, transport_factory=transport, resume=True
    )
    assert other["prior_attempt_ids"] and sent == [1]
