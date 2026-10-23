"""Real proof/central/control PG wiring; the production probe branch replaces only HTTP."""

from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from models.test_probe_delegated_pg import SOURCE, fixture_setup, session, substitute_live_boundary
from psycopg import sql

from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.quota_delegated import DEADLINE
from mingjing_core.models.quota_delegated_session import require_active
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.models.registry import ModelHandle, ModelRegistry
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock
from tools import probe_equivalence_delegated as delegated
from tools.eval import live as live_module
from tools.eval import runner
from tools.eval.model_selection import ProofSelectedRegistry, selected_model
from tools.eval.targets.v4_live import V4LiveTarget
from tools.eval.targets.v4_live_judge import V4LiveJudge
from tools.probe_equivalence_control import ProbeControl

from .test_eval_v4_live_pg import scenario, wire

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT.parent / "zhiming-v4/private/artifacts/kimi-k3-installer-20261023"


@pytest.fixture
def database(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    if not ARTIFACTS.is_dir():
        pytest.skip("requires installed local official K3 artifacts; never download")
    yield from fixture_setup.__wrapped__(p2_repo, monkeypatch)


@dataclass
class VerifiedFixture:
    database: Any
    args: Namespace
    environment: dict[str, str]
    equivalent: bool


@pytest.fixture
def prepare(database: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def build(*, equivalent: bool = True, mock: bool = False) -> VerifiedFixture:
        # Follow actual wall time instead of the probe helper's independent
        # future reference clock; business scenario time remains frozen separately.
        database.guard = QuotaGuard(**database.central)
        substitute_live_boundary(monkeypatch, fail_check=not equivalent)
        control, script = database.make_control(), session(database)
        transport = None
        if mock:
            from tools.probe_equivalence_mock import mock_transport

            def transport(case):
                return mock_transport(case, [])

        proof = delegated.run_delegated(
            database.base, script, control, source_sha256=SOURCE, transport_factory=transport
        )
        path = tmp_path / "synthetic-fixture-proof.json"
        path.write_text(json.dumps(proof), encoding="utf-8")
        args = Namespace(
            scripted_gate=tmp_path / "scripted-fixture.json",
            candidate=script.approval.candidate,
            equivalence_proof=path,
            control_schema=control.schema,
            resume=False,
            mode="live",
            target="v4",
            suite="core30",
        )
        monkeypatch.setattr(live_module, "candidate_gate", lambda *args: script.approval)
        monkeypatch.setattr(runner, "_source_digest", lambda: SOURCE)
        monkeypatch.setenv("PROBE_CONTROL_DSN", control.dsn)
        monkeypatch.setattr(ProbeControl, "initialize", lambda *args: pytest.fail("load must never perform DDL"))
        environment = {
            "MINGJING_AGENT_ENABLED": "true",
            "MODELS_CONFIG": str(ROOT / "config/models.yaml"),
            "K3_TOKENIZER_DIR": str(ARTIFACTS),
            "KIMI_API_KEY": "synthetic-proof-only",
            "KIMI_BASE_URL": "https://synthetic.invalid/v1",
            **{
                name: database.central[key]
                for key, name in {
                    "central_dsn": "MEMBER_CENTRAL_DSN",
                    "central_schema": "MEMBER_CENTRAL_SCHEMA",
                    "account_id": "MEMBER_ACCOUNT_ID",
                    "ledger_identity": "MEMBER_LEDGER_IDENTITY",
                }.items()
            },
        }
        for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
            monkeypatch.setenv(name, "1")
        for name, value in environment.items():
            if name.startswith("MEMBER_"):
                monkeypatch.setenv(name, value)
        return VerifiedFixture(database, args, environment, equivalent)

    return build


def core_attempts(fixture: VerifiedFixture) -> int:
    store = fixture.database.guard.store
    with store.connect() as connection:
        return connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {} WHERE lane='eval'").format(store.table("core_model_usage"))
        ).fetchone()["n"]


@pytest.mark.parametrize("equivalent", [True, False])
def test_verified_proof_selects_same_model_for_actual_agent_meter_and_external_judge(prepare, equivalent: bool) -> None:
    fixture = prepare(equivalent=equivalent)
    model = "k3-256k" if equivalent else "k3"
    original = ModelRegistry(environment=fixture.environment)
    before = (ROOT / "config/models.yaml").read_bytes()
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["model"])
        assert body["model"] == model and "thinking" not in body and "temperature" not in body
        if any(tool["name"] == "submit" for tool in body.get("tools", [])):
            return wire(
                {
                    "type": "tool_use",
                    "id": "judge-proof",
                    "name": "submit",
                    "input": {"score": 1.0, "verdict": "pass", "issues": []},
                }
            )
        return wire({"type": "text", "text": "合成已核对"})

    def factory(handle: ModelHandle):
        return handle.adapter(transport=httpx.MockTransport(respond), guard=require_active().guard, max_retries=0)

    target = V4LiveTarget(
        model=model, dsn=fixture.database.guard.store.dsn, environment=fixture.environment, adapter_factory=factory
    )
    try:
        with live_module.live_session(fixture.args, ["T01"]):
            selected = ProofSelectedRegistry(environment=fixture.environment)
            assert selected_model() == model
            for role in ("primary", "critic"):
                actual, configured = selected.resolve(role)[0], original.resolve(role)[0]
                assert (actual.model, actual.settings["model_lock"], actual.settings["effort"]) == (
                    model,
                    model,
                    "high",
                )
                assert (actual.base_url, actual.provider, actual.protocol, actual.caps) == (
                    configured.base_url,
                    configured.provider,
                    configured.protocol,
                    configured.caps,
                )
            judge = V4LiveJudge(
                model, ROOT / "tools/eval/rubric_v1.md", environment=fixture.environment, adapter_factory=factory
            )
            from tools.eval.engine import evaluate_scenario

            observed = evaluate_scenario(scenario(), target, target_name="v4", judge=judge)
            assert observed["status"] == "passed" and observed["model_calls"] == 2
            assert target.runtime.meter.model == target.runtime.ledger.base_meter.model == model
            assert target.runtime.reviewer.port is None
    finally:
        target.close()
    assert calls == [model, model] and core_attempts(fixture) == 2
    assert (ROOT / "config/models.yaml").read_bytes() == before
    assert all(original.resolve(role)[0].model == "k3-256k" for role in ("primary", "critic"))


def test_invalid_proof_variants_or_script_gate_issue_no_core_attempts(prepare, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = prepare()
    path = fixture.args.equivalence_proof
    actual = path.read_text(encoding="utf-8")
    proof = json.loads(actual)
    for changed in ({"equivalent": False}, {"complete": False}, {"source_sha256": "c" * 64}, {"account_id": "wrong"}):
        path.write_text(json.dumps({**proof, **changed}), encoding="utf-8")
        with pytest.raises(GuardRejected), live_module.live_session(fixture.args, ["T01"]):
            pytest.fail("invalid proof must never enter core scope")
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(GuardRejected), live_module.live_session(fixture.args, ["T01"]):
        pytest.fail("corrupt proof must not enter core scope")
    path.unlink()
    with pytest.raises(GuardRejected), live_module.live_session(fixture.args, ["T01"]):
        pytest.fail("missing proof must not enter core scope")
    path.write_text(actual, encoding="utf-8")
    monkeypatch.setattr(runner, "_source_digest", lambda: "c" * 64)
    with pytest.raises(GuardRejected), live_module.live_session(fixture.args, ["T01"]):
        pytest.fail("changed source must not enter core scope")
    monkeypatch.setattr(runner, "_source_digest", lambda: SOURCE)
    monkeypatch.setattr(
        live_module, "candidate_gate", lambda *args: (_ for _ in ()).throw(GuardRejected("manual_start_required"))
    )
    with pytest.raises(GuardRejected), live_module.live_session(fixture.args, ["T01"]):
        pytest.fail("scripted gate must precede core approval")
    assert core_attempts(fixture) == 0


def test_mock_proof_cannot_authorize_core_even_after_complete_twenty_checks(prepare) -> None:
    fixture = prepare(mock=True)
    with pytest.raises(GuardRejected), live_module.live_session(fixture.args, ["T01"]):
        pytest.fail("mock proof cannot authorize a production core scope")
    assert core_attempts(fixture) == 0


def test_expired_approval_and_absent_proof_parameters_fail_before_target(
    prepare, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare()
    with pytest.raises(GuardRejected), live_module.live_session(Namespace(), ["T01"]):
        pytest.fail("missing proof parameters must stop")
    # Keep the real PG guard/identity and move only its explicit test clock.
    fixture.database.guard.clock = FrozenClock(DEADLINE + timedelta(seconds=1))
    monkeypatch.setattr(live_module.CentralLocation, "guard", lambda self: fixture.database.guard)
    with pytest.raises(GuardRejected) as caught, live_module.live_session(fixture.args, ["T01"]):
        pytest.fail("expired receipt must stop before any target")
    assert caught.value.kind == "authorization_expired" and core_attempts(fixture) == 0


def test_model_selection_rejects_mixed_or_low_effort_source_configuration(prepare, tmp_path: Path) -> None:
    fixture = prepare(equivalent=False)
    configured = yaml.safe_load((ROOT / "config/models.yaml").read_text(encoding="utf-8"))
    path = tmp_path / "synthetic-mixed.yaml"
    configured["models"]["kimi-critic"]["model"] = "k3"
    configured["models"]["kimi-critic"]["settings"]["model_lock"] = "k3"
    environment = {**fixture.environment, "MODELS_CONFIG": str(path)}
    for low in (False, True):
        if low:
            configured["models"]["kimi-critic"]["model"] = "k3-256k"
            configured["models"]["kimi-critic"]["settings"].update(model_lock="k3-256k", effort="low")
        path.write_text(yaml.safe_dump(configured), encoding="utf-8")
        with live_module.live_session(fixture.args, ["T01"]), pytest.raises(ConfigError):
            ProofSelectedRegistry(environment=environment).resolve("primary")
    assert core_attempts(fixture) == 0


def test_cli_cannot_override_verified_model_or_create_a_fallback_chain(
    prepare, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = prepare(equivalent=False)
    seen = []
    monkeypatch.setattr(runner, "_run", lambda args, cases, config, model: seen.append(model) or 0)
    assert runner._run_models(fixture.args, [scenario()], {}, ["kimi"]) == 0 and seen == ["k3"]
    for models in (["k3-256k"], ["deepseek-main"], ["k3", "k3-256k"]):
        with pytest.raises(SystemExit):
            runner._run_models(fixture.args, [scenario()], {}, models)
    assert seen == ["k3"] and core_attempts(fixture) == 0


def test_live_resume_is_rejected_before_central_permit_target_or_post(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("live resume must stop before central access, target assembly or HTTP")

    args = Namespace(mode="live", target="v4", resume=True)
    monkeypatch.setattr(live_module.CentralLocation, "from_environment", forbidden)
    monkeypatch.setattr(live_module, "candidate_gate", forbidden)
    monkeypatch.setattr(runner, "_run", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    with pytest.raises(GuardRejected) as session_error, live_module.live_session(args, ["T01"]):
        pytest.fail("resume must not enter a live session")
    with pytest.raises(GuardRejected) as cli_error:
        runner._run_models(args, [scenario()], {}, ["kimi"])
    assert session_error.value.kind == cli_error.value.kind == "manual_start_required"
