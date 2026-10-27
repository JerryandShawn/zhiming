"""New writer/asset/admission wiring on an isolated PG, with an explicit synthetic exchange receipt."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from test_first_release_native_exchange_pg import sample as sample_fixture  # noqa: F401
from test_first_release_native_exchange_pg import set_closed
from test_first_release_stage_backup_pg import repo_for
from test_first_release_stage_prepare_pg import seed_prefix_four

from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.first_release_contracts import RestoreRejected, read_json
from tools.first_release_stage_app import stage_app
from tools.first_release_stage_runtime import admit, main, provision


@pytest.fixture
def runtime_target(tmp_path):
    generator = sample_fixture.__wrapped__(tmp_path)
    sample = next(generator)
    try:
        seed_prefix_four(sample)
        repo = repo_for(sample, sample.scope.original)
        try:
            repo.initialize()
            LangGraphRuntime(repo)
        finally:
            repo.close()
        set_closed(sample, sample.scope.original)
        yield sample
    finally:
        generator.close()
        with psycopg.connect(sample.admin, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(sample.scope.original + "_writer")))


def test_new_scram_writer_private_assets_explicit_admission_and_actual_health(runtime_target, tmp_path, monkeypatch):
    sample = runtime_target
    workspace = tmp_path / "assets"
    workspace.mkdir(mode=0o700)
    tokenizer = Path(os.environ["K3_TOKENIZER_ARTIFACT_DIR"])
    synthetic = dict(
        status="exchanged_closed",
        operation=sample.scope.operation,
        current_oid=sample.metadata["oid"],
        admission_opened=False,
    )
    receipt = provision(sample.scope, workspace, synthetic, "a" * 40, tokenizer, environment=sample.environment)
    assert receipt["status"] == "provisioned_closed" and not receipt["unit_installed"]
    config = read_json(workspace / "runtime.json")
    content = (workspace / "zhiming-core-fr-stage.service").read_text()
    assert config["token"] not in content and "password=" not in content
    assert "IPAddressDeny=any" in content and "SocketBindAllow=ipv4:tcp:8788" in content and "Restart=no" in content
    assert not any(key in config for key in ("KIMI_API_KEY", "MEMBER_CENTRAL_DSN", "MODELS_CONFIG"))
    with pytest.raises(RestoreRejected, match="STAGE_RUNTIME_CONFIG_CHANGED"):
        admit(sample.scope, workspace, dict(receipt, config_sha256="0" * 64), environment=sample.environment)
    assert not (workspace / "admitted-receipt.json").exists()
    result = admit(sample.scope, workspace, receipt, environment=sample.environment)
    assert result["status"] == "copy_database_admitted" and result["model_calls"] == 0
    monkeypatch.setenv("MINGJING_TOKEN", config["token"])
    repo = PostgresRepository(config["dsn"], initialize=False, max_size=3, max_running=3)
    app = stage_app(repo, sample.scope, config["database_oid"], workspace, tokenizer)
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"X-Token": config["token"]})
        assert response.status_code == 200 and response.json()["model"] == "stage-model-access-disabled"
        with repo.connection() as connection:
            assert not connection.execute(
                "SELECT has_schema_privilege(current_user,'mingjing_core','CREATE') AS ddl"
            ).fetchone()["ddl"]
    with pytest.raises(RestoreRejected, match="STAGE_RUNTIME_ALREADY_STARTED_NO_RETRY"):
        provision(sample.scope, workspace, synthetic, "a" * 40, tokenizer, environment=sample.environment)


def test_runtime_default_never_reads_receipts_or_connects(monkeypatch, tmp_path, capsys):
    import tools.first_release_stage_runtime as module

    def deny(*args, **kwargs):
        pytest.fail("validate-only may not consume private config or connect")

    monkeypatch.setattr(module, "file_hash", deny)
    assert (
        main(
            [
                "provision",
                "--operation",
                "b" * 16,
                "--workspace",
                str(tmp_path),
                "--receipt",
                str(tmp_path / "absent"),
                "--receipt-sha256",
                "c" * 64,
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == [] and '"database_connections": 0' in capsys.readouterr().out
