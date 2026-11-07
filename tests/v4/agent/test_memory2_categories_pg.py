"""Existing owner grants are honored without granting unrelated sensitive categories."""

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.repositories.postgres import PostgresRepository

from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def category_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def settings(repo: PostgresRepository, categories: object) -> None:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(repo.table("core_owners")),
            (Jsonb({"auto_save_low_sensitivity": True, "auto_save_categories": categories}), "alice"),
        )
        repo.bump_revision(connection, "alice", owner_scope=True)


@pytest.mark.parametrize("text", ["我最近失眠，想慢慢调整睡眠", "我这周复诊了"])
def test_granted_health_category_saves_via_real_v4_tool_without_reprompt(
    tool_repo: PostgresRepository, text: str
) -> None:
    settings(tool_repo, ["health"])
    h = setup(tool_repo, text)
    result, ctx, args = h.write("background")
    assert result.ok and result.receipt["write_status"] == "saved"
    assert tool_repo.list("alice", "proposal") == []
    before = tool_repo.get_revision("alice")
    assert h.registry.execute("memory_write", args, ctx).receipt == result.receipt
    assert tool_repo.get_revision("alice") == before


@pytest.mark.parametrize("categories", [[], ["money"], "health", None])
def test_ungranted_or_malformed_category_never_saves_health(tool_repo: PostgresRepository, categories: object) -> None:
    settings(tool_repo, categories)
    h = setup(tool_repo, "我最近失眠，想慢慢调整睡眠")
    result, _, _ = h.write("background")
    assert not result.ok and result.receipt["write_status"] == "pending_confirmation"
    assert tool_repo.list("alice", "fact") == []


def test_health_consent_does_not_authorize_third_party_health(tool_repo: PostgresRepository) -> None:
    settings(tool_repo, ["health"])
    h = setup(tool_repo, "我妈妈最近失眠，正在调整睡眠")
    result, _, _ = h.write("background")
    assert not result.ok and result.receipt["write_status"] == "pending_confirmation"
    assert tool_repo.list("alice", "fact") == []


def test_owner_optout_overrides_previously_granted_category(tool_repo: PostgresRepository) -> None:
    settings(tool_repo, ["health"])
    h = setup(tool_repo, "我最近失眠，这段不要记")
    result, _, _ = h.write("background")
    assert result.ok and result.receipt["write_status"] == "stopped"
    assert tool_repo.list("alice", "fact") == []
