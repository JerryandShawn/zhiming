"""A rehashed initial snapshot cannot replace the original case alias identity."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .case_status_write_support import prepare_write
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="write_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize(("field_name", "value"), [("revision", 2), ("id", "another-initial-case")])
def test_initial_alias_fields_are_rechecked_even_after_snapshot_hash_is_recomputed(
    write_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, field_name: str, value: str | int
) -> None:
    prepared = prepare_write(write_repo, monkeypatch)
    ident = f"{prepared.run['id']}:e0:agent_initial_context"
    with write_repo.transaction("alice") as connection:
        stored = connection.execute(
            sql.SQL("SELECT data FROM {} WHERE owner='alice' AND kind='runtime_step' AND id=%s").format(
                write_repo.table("core_entities")
            ),
            (ident,),
        ).fetchone()["data"]
        stored["output"]["alias_map"]["e1"][field_name] = value
        stored["output_sha256"] = fingerprint(stored["output"])
        connection.execute(
            sql.SQL("UPDATE {} SET data=%s WHERE owner='alice' AND kind='runtime_step' AND id=%s").format(
                write_repo.table("core_entities")
            ),
            (Jsonb(stored), ident),
        )
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()
