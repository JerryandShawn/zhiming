"""New-protocol witnesses survive usage updates and cannot borrow epochs or revisions."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_case_effect_marker import MARKER, PROTOCOL, SCHEMA
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository

from .case_effect_chain_support import effect_row, prepare_chain
from .case_status_write_support import prepare_write
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="boundary_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_deleting_new_proof_and_sequence_marker_cannot_downgrade_to_legacy_single_write(boundary_repo, monkeypatch):
    prepared = prepare_write(boundary_repo, monkeypatch)
    usage = boundary_repo.fetch_run("alice", prepared.run["id"])["usage"]
    assert usage[PROTOCOL] == {"0": SCHEMA}
    usage.pop(MARKER)
    with boundary_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE id=%s").format(boundary_repo.table("core_runs")),
            (Jsonb(usage), prepared.run["id"]),
        )
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE data->>'run_id'=%s AND data->>'schema'=%s").format(
                boundary_repo.table("core_entities")
            ),
            (prepared.run["id"], SCHEMA),
        )
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


def test_later_model_usage_and_finalization_preserve_body_free_case_protocol_witnesses(boundary_repo, monkeypatch):
    prepared = prepare_chain(boundary_repo, monkeypatch, count=3)
    usage = boundary_repo.fetch_run("alice", prepared.run["id"])["usage"]
    assert usage[MARKER] == {"0": {"schema": SCHEMA, "cases": {prepared.case["id"]: [2, 4, 6]}}}
    assert usage[PROTOCOL] == {"0": SCHEMA} and "agent_runtime" in usage
    prepared.finish()
    saved = boundary_repo.fetch_run("alice", prepared.run["id"])["usage"]
    assert saved[MARKER] == usage[MARKER] and saved[PROTOCOL] == usage[PROTOCOL]


@pytest.mark.parametrize("change", ["effect_epoch", "marker_epoch", "protocol_epoch", "same_body_new_revision"])
def test_current_chain_cannot_borrow_an_old_epoch_or_an_external_same_body_write(boundary_repo, monkeypatch, change):
    prepared = prepare_chain(boundary_repo, monkeypatch)
    row = effect_row(prepared, 2)
    with boundary_repo.transaction("alice") as connection:
        if change == "effect_epoch":
            connection.execute(
                sql.SQL("UPDATE {} SET data=jsonb_set(data,'{{epoch}}','1') WHERE id=%s").format(
                    boundary_repo.table("core_entities")
                ),
                (row["id"],),
            )
        elif change in {"marker_epoch", "protocol_epoch"}:
            usage = boundary_repo.fetch_run("alice", prepared.run["id"])["usage"]
            key = MARKER if change == "marker_epoch" else PROTOCOL
            usage[key]["1"] = usage[key].pop("0")
            connection.execute(
                sql.SQL("UPDATE {} SET usage=%s WHERE id=%s").format(boundary_repo.table("core_runs")),
                (Jsonb(usage), prepared.run["id"]),
            )
        else:
            current = boundary_repo.get("alice", "case", prepared.case["id"])
            boundary_repo.update(
                "alice", "case", current["id"], {"title": current["title"]}, expected_revision=current["revision"]
            )
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()
