"""Actual DML-only stage host, real public tokenizer and zero-provider HTTP boundaries."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_first_release_native_exchange_pg import sample as sample_fixture  # noqa: F401
from test_first_release_stage_backup_pg import repo_for
from test_first_release_stage_prepare_pg import seed_prefix_four

from mingjing_core.domain.consultation import ModelUnavailable
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.first_release_contracts import RestoreRejected
from tools.first_release_migration_steps import grant_new_runtime
from tools.first_release_stage_app import stage_app
from tools.first_release_writer_fence import file_lock


@pytest.fixture
def stage_runtime(tmp_path):
    generator = sample_fixture.__wrapped__(tmp_path)
    sample = next(generator)
    writer = sample.scope.original + "_writer"
    try:
        seed_prefix_four(sample)
        owner = repo_for(sample, sample.scope.original)
        try:
            owner.initialize()
            LangGraphRuntime(owner)
        finally:
            owner.close()
        with psycopg.connect(sample.admin, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT").format(sql.Identifier(writer)))
            admin.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path=public,pg_catalog").format(
                    sql.Identifier(writer), sql.Identifier(sample.scope.original)
                )
            )
        with psycopg.connect(make_conninfo(sample.admin, dbname=sample.scope.original), row_factory=dict_row) as admin:
            grant_new_runtime(admin, writer)
        yield sample, writer
    finally:
        generator.close()
        # Exact synthetic role only, after the fixture drops its own databases and ACL dependencies.
        with psycopg.connect(sample.admin, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(writer)))


def test_real_stage_host_installs_agent_but_only_allows_reads_and_holds_writer_fence(
    stage_runtime, tmp_path, monkeypatch
):
    sample, writer = stage_runtime
    monkeypatch.setenv("MINGJING_TOKEN", "SYNTHETIC_STAGE_TOKEN")
    workspace = tmp_path / "runtime"
    workspace.mkdir(mode=0o700)
    with file_lock(workspace / "writer.lock", exclusive=True):
        pass
    repo = PostgresRepository(
        make_conninfo(sample.admin, dbname=sample.scope.original, user=writer),
        initialize=False,
        max_size=3,
        max_running=3,
    )
    app = stage_app(
        repo, sample.scope, sample.metadata["oid"], workspace, Path(os.environ["K3_TOKENIZER_ARTIFACT_DIR"])
    )
    with TestClient(app) as client:
        service = app.state.service
        assert service.runtime_assembly.agent.meter.live_admissible
        assert service.runtime_assembly.agent.offline is False
        with pytest.raises(ModelUnavailable):
            service.runtime_assembly.agent.port.complete([])
        with pytest.raises(ModelUnavailable):
            service.model.generate(system="synthetic", payload={}, schema={}, purpose="synthetic")
        headers = {"X-Token": "SYNTHETIC_STAGE_TOKEN"}
        for path in ("/api/health", "/api/state", "/api/history"):
            assert client.get(path, headers=headers).status_code == 200
        assert client.get("/api/health").status_code == 401
        assert client.post("/api/consult", headers=headers, json={"message": "synthetic"}).status_code == 403
        assert client.get("/api/bazi", headers=headers).status_code == 403
        with (
            pytest.raises(RestoreRejected, match="INCREMENTAL_FILE_FENCE_BUSY"),
            file_lock(workspace / "writer.lock", exclusive=True),
        ):
            pytest.fail("active stage runtime must hold the actual shared writer fence")
        (workspace / "maintenance.json").write_text("{}", encoding="utf-8")
        assert client.get("/api/health", headers=headers).status_code == 503
    with file_lock(workspace / "writer.lock", exclusive=True):
        pass
