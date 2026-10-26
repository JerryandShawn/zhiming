"""Explicit P8 route uses actual isolated Charts with a native authorized snapshot."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from mingjing_core.application.agent_tools_charts import prepare_chart
from mingjing_core.application.charts_natal import P8InputsRequired
from mingjing_core.application.charts_service import ChartsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.p8_chart_service import P8CalculationUnavailable
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_computation_charts_pg import context, profile
from .test_toolkit_pg import SAID_AT, setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def prepare(repo: PostgresRepository):
    profile(repo)
    memory = MemoryService(repo)
    for field, value in (("birth.location.tz", "Asia/Shanghai"), ("birth.clock_basis", "clock")):
        text = f"请保存我的{field}为{value}"
        source = memory.receive("alice", content=text, source_id=field, at=SAID_AT)
        fact = memory.save_fact("alice", "self", source["id"], text, "profile", field=field, value=value)
        assert fact["write_status"] == "saved"
    h = setup(repo, "核对合成出生时间口径")
    _, ctx = context(h)
    return h, ctx, prepare_chart(h.service, ctx)


def test_real_p8_worker_route_returns_verified_owned_native_charts_without_writes(repo: PostgresRepository) -> None:
    h, ctx, snapshot = prepare(repo)
    before = deepcopy(snapshot)
    revision = repo.get_revision("alice")
    result = ChartsService().evaluate_time_basis("alice", "self", snapshot, "2026-10-27", operation_id=ctx.operation_id)
    assert snapshot == before and repo.get_revision("alice") == revision
    assert result["adapter_mode"] == "p8_v1_1"
    assert result["documents"][0]["scope"]["operation_id"] == ctx.operation_id
    assert result["documents"][0]["scope"]["revision"] == snapshot["revision"]
    assert result["calculation"]["charts"] and result["documents"][0]["references"]
    assert result["calculation"]["model_calls"] == result["calculation"]["writes"] == 0
    assert repo.list("alice", "artifact") == []
    h.finish()


def test_missing_or_unscoped_profile_never_invokes_worker(repo: PostgresRepository) -> None:
    h, ctx, snapshot = prepare(repo)

    def forbidden(owner):
        pytest.fail("Missing or unscoped profile must not start a calculator")

    current = deepcopy(snapshot)
    del current["profile"]["birth.location.tz"]
    with pytest.raises(P8InputsRequired):
        ChartsService().evaluate_time_basis(
            "alice", "self", current, "2026-10-27", operation_id=ctx.operation_id, p8_factory=forbidden
        )
    with pytest.raises(ScopeError):
        ChartsService().evaluate_time_basis(
            "bob", "self", snapshot, "2026-10-27", operation_id=ctx.operation_id, p8_factory=forbidden
        )
    h.finish()


def test_transport_error_is_fixed_safe_message_without_private_stderr(repo: PostgresRepository) -> None:
    h, ctx, snapshot = prepare(repo)

    def fail(request):
        raise RuntimeError("PRIVATE_BIRTH_STDERR")

    with pytest.raises(P8CalculationUnavailable) as error:
        ChartsService().evaluate_time_basis(
            "alice",
            "self",
            snapshot,
            "2026-10-27",
            operation_id=ctx.operation_id,
            p8_factory=lambda owner: SimpleNamespace(time_basis=fail),
        )
    assert "PRIVATE" not in str(error.value)
    assert repo.list("alice", "artifact") == []
    h.finish()
