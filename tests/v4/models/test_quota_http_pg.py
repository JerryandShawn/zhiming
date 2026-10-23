"""Physical adapter attempts use the real central PG guard with only HTTP replaced."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.models.errors import (
    ModelBadRequest,
    ModelCancelled,
    ModelUnavailable,
)
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_runtime import ENVIRONMENT, CallScope, call_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository

from .test_quota_guard_pg import configure_central


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return configure_central(p2_repo, monkeypatch)


def answer() -> httpx.Response:
    chunk = {
        "choices": [{"delta": {"content": "合成"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 2,
            "prompt_tokens_details": {"cached_tokens": 3},
        },
    }
    return httpx.Response(200, text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n")


def adapter(guard: QuotaGuard | None, handler: Any, **kwargs: Any) -> OpenAICompat:
    return OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="k3-256k",
        provider="kimi_code",
        settings={"membership": True},
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        guard=guard,
        **kwargs,
    )


def rows(guard: QuotaGuard) -> list[dict[str, Any]]:
    with guard.store.connect() as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} ORDER BY id").format(guard.store.table("core_model_usage"))
        ).fetchall()


def test_success_writes_one_physical_row_and_normalized_usage(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    port = adapter(guard, lambda _: answer())
    with call_scope(CallScope(run_id="synthetic-run")):
        assert port.complete([ChatMessage("user", "合成")]).text == "合成"
    records = rows(guard)
    assert len(records) == port.request_count == 1
    assert (
        records[0]["status"],
        records[0]["role"],
        records[0]["lane"],
        records[0]["run_id"],
    ) == (
        "ok",
        "primary",
        "interactive",
        "synthetic-run",
    )
    assert (
        records[0]["input_tokens"],
        records[0]["output_tokens"],
        records[0]["cache_read_tokens"],
    ) == (11, 2, 3)
    assert guard.status()["in_flight"] == 0
    assert "合成" not in str(records)


def test_every_retry_is_separately_admitted_and_recorded(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    port = adapter(guard, lambda _: httpx.Response(503))
    with pytest.raises(ModelUnavailable):
        port.complete([])
    assert port.request_count == 4
    assert [row["status"] for row in rows(guard)] == ["unavailable"] * 4
    assert guard.status()["in_flight"] == 0


@pytest.mark.parametrize(
    "message,kind",
    [
        ("Too many concurrent requests", "concurrency_limited"),
        ("Access terminated", "access_terminated"),
        ("You've reached your 5-hour usage limit.", "quota_5h"),
    ],
)
def test_terminal_provider_error_stops_all_subsequent_physical_posts(
    central: dict[str, Any],
    message: str,
    kind: str,
) -> None:
    guard = QuotaGuard(**central)
    sent = []

    def handler(_: httpx.Request) -> httpx.Response:
        sent.append(1)
        return httpx.Response(403, json={"error": {"type": "permission_error", "message": message}})

    with pytest.raises(ModelUnavailable):
        adapter(guard, handler).complete([])
    assert len(sent) == 1 and rows(guard)[0]["status"] == kind
    restarted = QuotaGuard(**central)
    with pytest.raises(GuardRejected):
        adapter(restarted, handler).complete([])
    assert len(sent) == 1 and restarted.status()["stop_kind"] == kind


def test_size_rejection_happens_before_admission_or_post(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    port = adapter(guard, lambda _: pytest.fail("no HTTP"))
    with pytest.raises(ModelBadRequest):
        port.complete([ChatMessage("user", "合成" * 400000)])
    assert rows(guard) == [] and port.request_count == 0


def test_eval_requires_active_manual_batch_and_cannot_claim_interactive(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    port = adapter(guard, lambda _: pytest.fail("no HTTP"))
    with call_scope(CallScope(lane="eval")), pytest.raises(GuardRejected) as error:
        port.complete([])
    assert error.value.kind == "manual_start_required" and rows(guard) == []


def test_two_live_streams_hold_both_slots_until_close(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    ready, release = threading.Barrier(3), threading.Event()

    def handler(_: httpx.Request) -> httpx.Response:
        ready.wait(timeout=5)
        assert release.wait(timeout=5)
        return answer()

    def request() -> str:
        return adapter(guard, handler).complete([]).text

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(request) for _ in range(2)]
        try:
            ready.wait(timeout=5)
            assert guard.status()["in_flight"] == 2
            with (
                pytest.raises(GuardRejected, match="会员调用暂已停止"),
                guard.acquire(
                    "primary",
                    "interactive",
                    attempt_id="third",
                    provider="kimi_code",
                    model="k3",
                    timeout=0,
                ),
            ):
                pytest.fail("third slot must be refused")
        finally:
            release.set()
        assert [future.result(timeout=5) for future in futures] == ["合成", "合成"]
    assert len(rows(guard)) == 2 and guard.status()["in_flight"] == 0


def test_consumer_close_releases_slot_and_keeps_conservative_usage(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    stream = adapter(guard, lambda _: answer()).stream([])
    while next(stream).type != "text":
        continue
    assert guard.status()["in_flight"] == 1
    stream.close()
    assert guard.status()["in_flight"] == 0
    assert len(rows(guard)) == 1 and rows(guard)[0]["status"] == "unknown"


def test_cancel_after_visible_fragment_finishes_ledger_and_releases_slot(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    cancel = threading.Event()
    stream = adapter(guard, lambda _: answer()).stream([], cancel_event=cancel)
    while next(stream).type != "text":
        continue
    cancel.set()
    with pytest.raises(ModelCancelled):
        next(stream)
    assert guard.status()["in_flight"] == 0 and rows(guard)[0]["status"] == "cancelled"


def test_sse_terminal_error_persists_global_stop(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    event = {"error": {"type": "permission_error", "message": "Access terminated"}}
    port = adapter(guard, lambda _: httpx.Response(200, text="data: " + json.dumps(event) + "\n\n"))
    with pytest.raises(ModelUnavailable):
        port.complete([])
    assert port.request_count == 1 and rows(guard)[0]["status"] == "access_terminated"
    assert guard.status()["stop_kind"] == "access_terminated" and guard.status()["in_flight"] == 0


def test_constructed_critic_keeps_critic_partition(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    port = OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="k3",
        provider="kimi_code",
        settings={"membership": True, "role_binding": "critic"},
        transport=httpx.MockTransport(lambda _: answer()),
        guard=guard,
    )
    assert port.complete([], role="critic").text == "合成"
    assert (rows(guard)[0]["role"], rows(guard)[0]["bucket"]) == ("critic", "critic")


def test_runtime_loads_explicit_central_identity_before_substituted_http(
    central: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, name in ENVIRONMENT.items():
        monkeypatch.setenv(name, central[key])

    class Substitute(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return answer()

    port = OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="k3",
        provider="kimi_code",
        transport=Substitute(),
    )
    assert port.complete([]).text == "合成"
    assert len(rows(QuotaGuard(**central))) == port.request_count == 1
