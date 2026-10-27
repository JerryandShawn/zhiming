"""Native local restore keeps the original central ledger; HTTP is synthetic only."""

from __future__ import annotations

import json
import os
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import httpx
import psycopg
import pytest
from first_release_support import ROOT
from models.test_quota_guard_batches_pg import begin, evaluated
from models.test_quota_guard_pg import configure_central, provision
from models.test_u39_anthropic_wire import block_record
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_first_release_local_restore_pg import sample as local_restore_sample

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.models.port import ChatMessage
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_mode import current_delegated_session
from mingjing_core.models.quota_runtime import ENVIRONMENT, CallScope, call_scope
from mingjing_core.models.quota_store import QuotaStore
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.models.registry import RegistryPort
from mingjing_core.repositories.permissions import grant_runtime_tables
from tools.first_release_local_restore import execute

TABLES = ("core_model_accounts", "core_model_usage", "core_model_batches", "core_model_authorizations")
RUN = "synthetic-restored-business-routing"


@pytest.fixture(name="sample")
def restored_sample(request, tmp_path_factory):
    yield from local_restore_sample.__wrapped__(request, tmp_path_factory)


def ledger_state(dsn, schema):
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        tables = {}
        for name in TABLES:
            tables[name] = [
                row["value"]
                for row in connection.execute(
                    sql.SQL('SELECT to_jsonb(t) AS value FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(
                        sql.Identifier(schema, name)
                    )
                ).fetchall()
            ]
        sequence = connection.execute(
            sql.SQL("SELECT last_value,log_cnt,is_called FROM {}").format(
                sql.Identifier(schema, "core_model_usage_id_seq")
            )
        ).fetchone()
    return {"tables": tables, "sequence": sequence}


@contextmanager
def original_central(repo, monkeypatch):
    values = configure_central(repo, monkeypatch)
    guard = QuotaGuard(**values)
    begin(guard)
    assert evaluated(guard, "synthetic-historical-attempt") == [1]
    guard.finish_batch("batch-1", "manual-start-1")
    stopped = dict(values, account_id="synthetic-stopped", ledger_identity=str(uuid.uuid4()))
    provision(stopped)
    QuotaGuard(**stopped).record_stop("access_terminated")
    role, clone = "quota_route_" + uuid.uuid4().hex, "quota_clone_" + uuid.uuid4().hex
    with repo.transaction() as connection:
        connection.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(sql.Identifier(role))
        )
    try:
        with repo.transaction() as connection:
            grant_runtime_tables(connection, role, repo.schema)
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(clone)))
            connection.execute(
                sql.SQL("CREATE TABLE {} (LIKE {} INCLUDING ALL)").format(
                    sql.Identifier(clone, "core_model_accounts"), repo.table("core_model_accounts")
                )
            )
            connection.execute(
                sql.SQL("INSERT INTO {} SELECT * FROM {}").format(
                    sql.Identifier(clone, "core_model_accounts"), repo.table("core_model_accounts")
                )
            )
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(*map(sql.Identifier, (clone, role))))
            connection.execute(
                sql.SQL("GRANT SELECT ON {} TO {}").format(
                    sql.Identifier(clone, "core_model_accounts"), sql.Identifier(role)
                )
            )
        runtime = dict(values, central_dsn=make_conninfo(values["central_dsn"], options=f"-c role={role}"))
        yield runtime, dict(stopped, central_dsn=runtime["central_dsn"]), clone
    finally:
        with repo.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(clone)))
            connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def install_process(monkeypatch, restored, central):
    directory = Path(os.environ.get("K3_TOKENIZER_ARTIFACT_DIR", ""))
    assert directory.is_absolute() and directory.is_dir(), "ACTUAL_LOCAL_OFFICIAL_K3_ARTIFACT_REQUIRED"
    environment = {
        "ZHIMING_DATABASE_URL": restored.environment["FIRST_RELEASE_WRITER_DSN"],
        "CORE_RUN_CONCURRENCY": "3",
        "CORE_DB_POOL_SIZE": "4",
        "MINGJING_AGENT_ENABLED": "true",
        "MODELS_CONFIG": str(ROOT / "config/models.yaml"),
        "K3_TOKENIZER_DIR": str(directory),
        "KIMI_API_KEY": "synthetic-central-routing-only",
        "KIMI_BASE_URL": "https://synthetic.invalid/v1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
    }
    environment.update({name: central[key] for key, name in ENVIRONMENT.items()})
    for name, value in environment.items():
        monkeypatch.setenv(name, value)


class SyntheticWire(httpx.BaseTransport):
    """A non-Mock outer transport deliberately retains the real from-env guard."""

    def __init__(self):
        self.sent = []
        self.mock = httpx.MockTransport(self.respond)

    def respond(self, request):
        assert request.method == "POST" and request.url.host == "synthetic.invalid"
        self.sent.append(1)
        return httpx.Response(200, content=block_record([{"type": "text", "text": "合成恢复后答复"}]))

    def handle_request(self, request):
        return self.mock.handle_request(request)


def forbid_runtime_bootstrap(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("RUNTIME_MUST_NOT_PROVISION_CLEAR_OR_USE_REAL_NETWORK")

    monkeypatch.setattr(QuotaStore, "provision", forbidden)
    monkeypatch.setattr(QuotaGuard, "clear_stop", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def call_actual_service(restored, wire):
    assert current_delegated_session() is None
    service = ConsultationService.from_base()
    try:
        with service.repo.transaction() as connection:
            identity = connection.execute("SELECT current_database() AS db,current_user AS role").fetchone()
        database = restored.inputs.contract.database
        assert identity == {"db": database, "role": database + "_writer"}
        agent = service.runtime_assembly.require_agent()
        assert agent.offline is False and agent.meter.live_admissible is True
        assert isinstance(agent.port, RegistryPort)

        def factory(handle):
            adapter = handle.adapter(max_retries=0, transport=wire)
            assert adapter.guard is None and not isinstance(adapter.transport, httpx.MockTransport)
            return adapter

        agent.port.factory = factory
        with call_scope(CallScope(run_id=RUN)):
            return agent.port.complete([ChatMessage("user", "合成业务恢复后的路由校验")])
    finally:
        service.repo.close()


def assert_only_one_append(before, after, central):
    old, new = before["tables"], after["tables"]
    assert new["core_model_batches"] == old["core_model_batches"]
    assert new["core_model_authorizations"] == old["core_model_authorizations"]
    previous = {row["id"]: row for row in old["core_model_usage"]}
    current = {row["id"]: row for row in new["core_model_usage"]}
    assert all(current.get(key) == row for key, row in previous.items())
    added = [row for key, row in current.items() if key not in previous]
    assert len(added) == 1
    row = added[0]
    assert row["account_id"] == central["account_id"] and row["attempt_id"].startswith("http-")
    assert uuid.UUID(row["attempt_id"][5:]).hex == row["attempt_id"][5:]
    assert (row["run_id"], row["provider"], row["model"], row["role"], row["status"]) == (
        RUN,
        "kimi_code",
        "k3-256k",
        "primary",
        "ok",
    )
    assert row["finished_at"] is not None and row["input_tokens"] == 5
    assert (row["lane"], row["bucket"], row["batch_id"], row["scenario_id"]) == (
        "interactive",
        "interactive",
        None,
        None,
    )
    assert row["id"] == before["sequence"]["last_value"] + 1 == after["sequence"]["last_value"]
    assert after["sequence"]["is_called"] is True
    accounts = {row["account_id"]: row for row in new["core_model_accounts"]}
    assert set(accounts) == {row["account_id"] for row in old["core_model_accounts"]}
    for original in old["core_model_accounts"]:
        actual = accounts[original["account_id"]]
        if original["account_id"] == central["account_id"]:
            assert {key: value for key, value in actual.items() if key != "last_clock_at"} == {
                key: value for key, value in original.items() if key != "last_clock_at"
            }
            assert datetime.fromisoformat(actual["last_clock_at"]) >= datetime.fromisoformat(original["last_clock_at"])
        else:
            assert actual == original


def reject_bad_startups(monkeypatch, restored, clone, wire):
    changes = (
        {"central_dsn": restored.environment["FIRST_RELEASE_WRITER_DSN"], "central_schema": "mingjing_core"},
        {"ledger_identity": str(uuid.uuid4())},
        {"central_schema": clone},
    )
    for changed in changes:
        with monkeypatch.context() as local:
            for key, value in changed.items():
                local.setenv(ENVIRONMENT[key], value)
            with pytest.raises(GuardRejected) as caught:
                call_actual_service(restored, wire)
            assert caught.value.kind == "ledger_unavailable"


@pytest.mark.parametrize("sample", [7], indirect=True)
def test_actual_restored_business_uses_original_nonempty_central_and_refuses_wrong_bindings(
    sample, p2_repo, monkeypatch, record_property
):
    with original_central(p2_repo, monkeypatch) as (central, stopped, clone):
        before = ledger_state(p2_repo.dsn, p2_repo.schema)
        assert all(before["tables"][table] for table in TABLES)
        result = execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
        assert result["local_upgrade_completed"] is result["runtime_acl_verified"] is True
        assert result["central_binding_verified"] is result["central_provisioned"] is False
        assert ledger_state(p2_repo.dsn, p2_repo.schema) == before
        business = ledger_state(sample.environment["FIRST_RELEASE_OWNER_DSN"], "mingjing_core")
        assert all(not business["tables"][table] for table in TABLES) and business["sequence"]["is_called"] is False
        install_process(monkeypatch, sample, central)
        forbid_runtime_bootstrap(monkeypatch)
        wire = SyntheticWire()
        assert call_actual_service(sample, wire).text == "合成恢复后答复" and wire.sent == [1]
        after = ledger_state(p2_repo.dsn, p2_repo.schema)
        assert_only_one_append(before, after, central)
        assert ledger_state(sample.environment["FIRST_RELEASE_OWNER_DSN"], "mingjing_core") == business
        reject_bad_startups(monkeypatch, sample, clone, wire)
        with monkeypatch.context() as local:
            for key, name in ENVIRONMENT.items():
                local.setenv(name, stopped[key])
            with pytest.raises(GuardRejected) as caught:
                call_actual_service(sample, wire)
            assert caught.value.kind == "access_terminated" and caught.value.global_stop is True
        assert wire.sent == [1] and ledger_state(p2_repo.dsn, p2_repo.schema) == after
        assert ledger_state(sample.environment["FIRST_RELEASE_OWNER_DSN"], "mingjing_core") == business
        record_property("native_local_restore_upgrade", True)
        record_property("original_central_added_uuid_count", 1)
        record_property("rejected_binding_and_stop_count", 4)
        record_property("runtime_provision_count", 0)
        record_property("actual_external_requests", 0)
        record_property("formal_central_rebinding_verified", False)
        assert "synthetic-central-routing-only" not in json.dumps(result)
