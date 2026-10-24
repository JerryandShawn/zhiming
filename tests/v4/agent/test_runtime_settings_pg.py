"""Real isolated PostgreSQL proves routing CAS, durable replay and rollback."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.runtime_settings import OPERATION, RuntimeSettingsService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import ScriptedPort
from .test_runtime_assembly_pg import service


@pytest.fixture(autouse=True)
def no_model_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args: object, **kwargs: object) -> None:
        pytest.fail("Runtime settings tests forbid all HTTP/model requests")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)


def state(repo: PostgresRepository, owner: str = "alice") -> dict:
    with repo.transaction() as connection:
        return connection.execute(
            sql.SQL("SELECT revision,settings FROM {} WHERE id=%s").format(
                repo.table("core_owners")
            ),
            (owner,),
        ).fetchone()


def requests(repo: PostgresRepository) -> int:
    with repo.transaction() as connection:
        return connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {} WHERE operation=%s").format(
                repo.table("core_mutation_requests")
            ),
            (OPERATION,),
        ).fetchone()["n"]


def test_preview_is_read_only_and_apply_routes_new_runs_both_directions(
    p2_repo: PostgresRepository,
) -> None:
    repo = p2_repo
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=settings||%s WHERE id='alice'").format(
                repo.table("core_owners")
            ),
            (
                Jsonb(
                    {"theme": "synthetic", "nested": {"keep": [1, 2]}, "enabled": False}
                ),
            ),
        )
    manager, core = RuntimeSettingsService(repo), service(repo, ScriptedPort([]))
    before = state(repo)
    old = core.submit(owner="alice", request_id="switch-before", message="合成原路径")
    revision = state(repo)["revision"]
    preview = manager.preview("alice", "v4")
    assert (
        preview["mode"] == "dry-run"
        and preview["would_change"] is True
        and preview["changed"] is False
    )
    assert state(repo)["settings"] == before["settings"] and requests(repo) == 0
    enabled = manager.apply(
        "alice", "v4", expected_runtime="v3", request_id="switch-up"
    )
    assert enabled["changed"] is True and enabled["replayed"] is False
    newer = core.submit(owner="alice", request_id="switch-new", message="合成新路径")
    assert old["runtime"] == "v3" and newer["runtime"] == "v4"
    assert (
        core.submit(owner="alice", request_id="switch-before", message="合成原路径")[
            "runtime"
        ]
        == "v3"
    )
    manager.apply("alice", "v3", expected_runtime="v4", request_id="switch-down")
    after = core.submit(
        owner="alice", request_id="switch-after", message="合成回切路径"
    )
    assert after["runtime"] == "v3"
    assert (
        core.submit(owner="alice", request_id="switch-new", message="合成新路径")[
            "runtime"
        ]
        == "v4"
    )
    assert state(repo)["settings"] == dict(before["settings"], runtime="v3")
    assert repo.fetch_run("alice", old["id"])["runtime"] == "v3"
    assert revision <= state(repo)["revision"] and requests(repo) == 2
    assert core.runtime_assembly.agent.port.requests == []


def test_exact_replay_after_further_changes_is_a_no_write_receipt(
    p2_repo: PostgresRepository,
) -> None:
    manager = RuntimeSettingsService(p2_repo)
    first = manager.apply("alice", "v4", expected_runtime="v3", request_id="replay-up")
    manager.apply("alice", "v3", expected_runtime="v4", request_id="replay-down")
    before = state(p2_repo)
    repeated = manager.apply(
        "alice", "v4", expected_runtime="v3", request_id="replay-up"
    )
    assert first["original_changed"] is True
    assert repeated["replayed"] is True and repeated["changed"] is False
    assert repeated["old_runtime"] == "v3" and repeated["new_runtime"] == "v4"
    assert repeated["current_runtime"] == "v3"
    assert state(p2_repo) == before and requests(p2_repo) == 2


def test_conflicting_intent_or_expected_value_does_not_write(
    p2_repo: PostgresRepository,
) -> None:
    manager = RuntimeSettingsService(p2_repo)
    manager.apply("alice", "v4", expected_runtime="v3", request_id="stable")
    before = state(p2_repo)
    with pytest.raises(EvidenceError, match="different intent"):
        manager.apply("alice", "v3", expected_runtime="v4", request_id="stable")
    with pytest.raises(RevisionConflict):
        manager.apply("alice", "v3", expected_runtime="v3", request_id="stale")
    assert state(p2_repo) == before and requests(p2_repo) == 1


def test_unknown_owner_and_revoked_self_do_not_create_owner(
    p2_repo: PostgresRepository,
) -> None:
    manager = RuntimeSettingsService(p2_repo)
    with pytest.raises(ScopeError):
        manager.preview("not-created", "v4")
    with pytest.raises(ScopeError):
        manager.apply("not-created", "v4", expected_runtime="v3", request_id="unknown")
    with p2_repo.transaction() as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT 1 FROM {} WHERE id='not-created'").format(
                    p2_repo.table("core_owners")
                )
            ).fetchone()
            is None
        )
        connection.execute(
            sql.SQL(
                "UPDATE {} SET consent='revoked' WHERE owner='alice' AND id='self'"
            ).format(p2_repo.table("core_subjects"))
        )
    with pytest.raises(ScopeError):
        manager.apply("alice", "v4", expected_runtime="v3", request_id="revoked")
    assert requests(p2_repo) == 0


def test_noop_retains_settings_and_owner_revision(p2_repo: PostgresRepository) -> None:
    before = state(p2_repo)
    receipt = RuntimeSettingsService(p2_repo).apply(
        "alice", "v3", expected_runtime="v3", request_id="noop"
    )
    assert receipt["changed"] is False and receipt["original_changed"] is False
    assert state(p2_repo) == before and requests(p2_repo) == 1


def test_concurrent_old_value_precondition_allows_exactly_one_writer(
    p2_repo: PostgresRepository,
) -> None:
    barrier = Barrier(2)

    def change(request_id: str) -> str:
        barrier.wait(timeout=5)
        try:
            RuntimeSettingsService(p2_repo).apply(
                "alice", "v4", expected_runtime="v3", request_id=request_id
            )
        except RevisionConflict:
            return "conflict"
        return "updated"

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(change, ["concurrent-a", "concurrent-b"]))
    assert sorted(results) == ["conflict", "updated"]
    assert state(p2_repo)["settings"]["runtime"] == "v4" and requests(p2_repo) == 1


@pytest.mark.parametrize("runtime", ["v5", "", None, True])
def test_invalid_runtime_is_rejected_without_writes(
    p2_repo: PostgresRepository, runtime: object
) -> None:
    with pytest.raises(EvidenceError):
        RuntimeSettingsService(p2_repo).preview("alice", runtime)
    assert requests(p2_repo) == 0


def test_owner_change_does_not_change_bobs_settings_or_existing_revisions(
    p2_repo: PostgresRepository,
) -> None:
    alice, bob = state(p2_repo), state(p2_repo, "bob")
    RuntimeSettingsService(p2_repo).apply(
        "alice", "v4", expected_runtime="v3", request_id="isolated"
    )
    assert state(p2_repo)["revision"] == alice["revision"]
    assert state(p2_repo, "bob") == bob


@pytest.mark.parametrize("value", [None, True, "v5", ["v4"]])
def test_invalid_persisted_runtime_is_not_repaired_or_overwritten(
    p2_repo: PostgresRepository, value: object
) -> None:
    with p2_repo.transaction() as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=settings||%s WHERE id='alice'").format(
                p2_repo.table("core_owners")
            ),
            (Jsonb({"runtime": value}),),
        )
    before = state(p2_repo)
    manager = RuntimeSettingsService(p2_repo)
    with pytest.raises(EvidenceError):
        manager.preview("alice", "v4")
    with pytest.raises(EvidenceError):
        manager.apply("alice", "v4", expected_runtime="v3", request_id="invalid-state")
    assert state(p2_repo) == before and requests(p2_repo) == 0


def test_receipt_insert_failure_rolls_back_route_update_in_real_pg(
    p2_repo: PostgresRepository,
) -> None:
    with p2_repo.transaction() as connection:
        connection.execute(
            sql.SQL(
                "ALTER TABLE {} ADD CONSTRAINT reject_runtime CHECK(operation <> {})"
            ).format(p2_repo.table("core_mutation_requests"), sql.Literal(OPERATION)),
        )
    before = state(p2_repo)
    with pytest.raises(psycopg.errors.CheckViolation):
        RuntimeSettingsService(p2_repo).apply(
            "alice", "v4", expected_runtime="v3", request_id="rollback"
        )
    assert state(p2_repo) == before and requests(p2_repo) == 0


def test_concurrent_exact_request_replays_once(p2_repo: PostgresRepository) -> None:
    barrier = Barrier(2)

    def change(_: int) -> dict:
        barrier.wait(timeout=5)
        return RuntimeSettingsService(p2_repo).apply(
            "alice", "v4", expected_runtime="v3", request_id="same-key"
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(change, [0, 1]))
    assert sorted(result["changed"] for result in results) == [False, True]
    assert sorted(result["replayed"] for result in results) == [False, True]
    assert requests(p2_repo) == 1 and state(p2_repo)["settings"]["runtime"] == "v4"
