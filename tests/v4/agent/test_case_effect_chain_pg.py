"""Current complete revision chains are accepted; gaps and forged historical bytes are not."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_case_effect_marker import MARKER
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository

from .case_effect_chain_support import effect_row, prepare_chain, replace_effect
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="chain_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("count", [2, 3])
@pytest.mark.parametrize("same_response", [False, True])
@pytest.mark.parametrize("status", ["paused", "closed"])
def test_multiple_case_revisions_have_a_complete_current_chain(
    chain_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, count: int, same_response: bool, status: str
) -> None:
    prepared = prepare_chain(chain_repo, monkeypatch, count=count, same_response=same_response, status=status)
    result = prepared.finish()
    assert result["text"] == "事项多次更新〔e1〕" and len(result["receipts"]) == count
    assert all(receipt["write_status"] == "saved" for receipt in result["receipts"])


@pytest.mark.parametrize("sequence", [2, 4])
@pytest.mark.parametrize(
    "change", ["missing", "before", "after", "update_input", "operation_digest", "arguments", "metadata"]
)
def test_missing_or_rehashed_corrupt_effects_cannot_authorize_a_chain(
    chain_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, sequence: int, change: str
) -> None:
    prepared = prepare_chain(chain_repo, monkeypatch)
    row = effect_row(prepared, sequence)
    if change in {"missing", "metadata"}:
        with chain_repo.transaction("alice") as connection:
            statement = (
                "DELETE FROM {} WHERE id=%s"
                if change == "missing"
                else ("UPDATE {} SET data=jsonb_set(data,'{{seq}}','99'::jsonb) WHERE id=%s")
            )
            connection.execute(sql.SQL(statement).format(chain_repo.table("core_entities")), (row["id"],))
    else:
        output = row["output"]
        if change in {"before", "after", "update_input"}:
            output[change]["title"] = "伪造历史标题"
        elif change == "operation_digest":
            output["operation_fingerprint"] = "0" * 64
        else:
            output["arguments"]["changes"]["goal"] = "伪造目标"
        replace_effect(prepared, sequence, output)
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


@pytest.mark.parametrize("change", ["missing", "gap", "duplicate", "reversed", "schema", "extra"])
def test_run_marker_cannot_downgrade_or_hide_chain_revisions(
    chain_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    prepared = prepare_chain(chain_repo, monkeypatch)
    run = chain_repo.fetch_run("alice", prepared.run["id"])
    usage = run["usage"]
    if change == "missing":
        usage.pop(MARKER)
    elif change == "schema":
        usage[MARKER]["0"]["schema"] = "unsupported"
    else:
        usage[MARKER]["0"]["cases"][prepared.case["id"]] = {
            "gap": [4],
            "duplicate": [2, 2, 4],
            "reversed": [4, 2],
            "extra": [2, 3, 4],
        }[change]
    with chain_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE id=%s").format(chain_repo.table("core_runs")),
            (Jsonb(usage), prepared.run["id"]),
        )
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


@pytest.mark.parametrize("field", ["before", "after", "update_input", "versions", "context_source_ids", "arguments"])
def test_rehashed_malformed_private_structure_is_rejected_without_raw_exception(chain_repo, monkeypatch, field):
    prepared = prepare_chain(chain_repo, monkeypatch)
    output = effect_row(prepared, 2)["output"]
    output[field] = None
    replace_effect(prepared, 2, output)
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()
