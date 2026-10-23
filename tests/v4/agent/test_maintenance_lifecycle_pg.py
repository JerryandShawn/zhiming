"""A failed bounded maintenance sweep is observable while the legacy worker continues."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.maintenance_schedule import FAILURE_CODE
from mingjing_core.application.privacy_maintenance import PrivacyMaintenance
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_pg_channels import FixtureModel

from .test_dispatcher_pg import until
from .test_thread_routes_pg import repository_fixture as source_repo_fixture


@pytest.fixture(name="maintenance_http_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_sweep_failure_preserves_v3_worker_and_stays_throttled(
    maintenance_http_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    repo = maintenance_http_repo
    core = ConsultationService(repo, model=FixtureModel())
    app = create_app(core)
    calls: list[int] = []

    def fail(self: PrivacyMaintenance, *, limit: int) -> dict[str, int]:
        calls.append(limit)
        raise RuntimeError("PRIVATE_MAINTENANCE_TRANSPORT_BODY")

    monkeypatch.setattr(PrivacyMaintenance, "tick", fail)
    run = core.submit(owner="alice", request_id="maintenance-worker", message="合成旧版学习问题", depth="fast")
    try:
        with TestClient(app):
            until(lambda: repo.fetch_run("alice", run["id"])["status"] == "succeeded")
            schedule = app.state.core["maintenance"]
            assert schedule.failures == 1 and schedule.last_error_code == FAILURE_CODE
            assert core.repo.fetch_run("alice", run["id"])["result"]["schema_version"] == "core3.0"
            assert calls == [50] and app.state.core["dispatcher"] is None
        assert FAILURE_CODE in caplog.text and "PRIVATE_MAINTENANCE_TRANSPORT_BODY" not in caplog.text
    finally:
        core.runtime.purge(run["id"], 0)
