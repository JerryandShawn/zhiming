"""An idle archive sweep must not invalidate an unchanged user's HTTP revision."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.memory2_background_archive import MemoryArchiveSweep
from mingjing_core.timekit.clock import FrozenClock
from tests.test_core_pg_channels import FixtureModel

from .test_memory2_archive_pg import event
from .test_memory2_schedule_pg import scheduled as scheduled_fixture


@pytest.fixture(name="scheduled")
def archive_schedule(p2_repo, monkeypatch):
    return scheduled_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("has_future_event", [False, True])
def test_no_due_facts_leave_owner_revision_and_entities_unchanged(scheduled, has_future_event):
    repo, _ = scheduled
    if has_future_event:
        event(repo)
    clock = FrozenClock(datetime.fromisoformat("2026-10-18T10:00:00+08:00"))
    sweep = MemoryArchiveSweep(repo, clock)
    before = repo.get_revision("alice")
    records = repo.list("alice", "runtime_step")
    facts = repo.list("alice", "fact")
    for _ in range(2):
        assert sweep.owner("alice") == {"archived": 0, "skipped": 0}
        assert repo.get_revision("alice") == before
        assert repo.list("alice", "runtime_step") == records
        assert repo.list("alice", "fact") == facts


def test_noop_page_keeps_bounded_progress_to_later_due_fact(scheduled):
    repo, _ = scheduled
    _, due, _ = event(repo)
    with repo.transaction("alice"):
        for index in range(100):
            repo.put("alice", "fact", f"a-no-expiry-{index:03}", {"content": "合成无到期事实"})
    clock = FrozenClock(datetime.fromisoformat("2026-10-22T10:00:00+08:00"))
    sweep = MemoryArchiveSweep(repo, clock)
    before = repo.get_revision("alice")
    assert sweep.owner("alice") == {"archived": 0, "skipped": 0}
    assert repo.get_revision("alice") == before
    assert sweep.owner("alice")["archived"] == 1
    assert repo.get("alice", "fact", due["id"])["status"] == "archived"


@pytest.mark.parametrize("action", ["profile", "settings"])
def test_native_http_confirmation_survives_noop_sweep_but_rejects_wrong_revision(scheduled, monkeypatch, action):
    repo, _ = scheduled
    clock = FrozenClock(datetime.fromisoformat("2026-10-18T10:00:00+08:00"))
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-token")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    core = ConsultationService(repo, model=FixtureModel())
    headers = {"X-Token": "synthetic-token"}
    with TestClient(create_app(core)) as client:
        revision = client.get("/api/state", headers=headers).json()["revision"]
        assert MemoryArchiveSweep(repo, clock).owner("alice")["archived"] == 0
        body = {"request_id": "noop-confirm", "expected_revision": revision}
        if action == "profile":
            body.update(confirmed=True, profile={"gender": "女"})
            method, path = client.post, "/api/subjects/self/profile/confirm"
        else:
            body["settings"] = {"auto_save_low_sensitivity": False}
            method, path = client.patch, "/api/state/settings"
        wrong = dict(body, request_id="wrong-revision", expected_revision=revision + 1)
        assert method(path, headers=headers, json=wrong).status_code == 409
        response = method(path, headers=headers, json=body)
        assert response.status_code == 200, response.text
