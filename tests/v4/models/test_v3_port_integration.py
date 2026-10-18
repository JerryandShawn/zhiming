"""The opt-in shim runs the real v3 service/PG; only provider HTTP is replaced."""

import json
import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.models.errors import ModelQuotaExhausted
from mingjing_core.models.legacy import PortBackedModel
from tests.test_core_pg_channels import FixtureModel
from tools.eval.targets.v3_target import V3Target

from .test_protocols import adapter, recording
from .test_schema_registry import registry


@pytest.fixture
def target(tmp_path: Any) -> Iterator[tuple[V3Target, PortBackedModel]]:
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable PostgreSQL 15")
    model_registry = registry(tmp_path)
    model_registry.data["roles"]["primary"] = ["a"]
    shim = PortBackedModel(model_registry)
    instance = V3Target(dsn=dsn, provider=shim)
    instance.reset({"profile": "empty_profile", "facts": [], "thread": [], "_scenario_id": "R02"})
    try:
        yield instance, shim
    finally:
        instance.close()


def test_real_service_submit_shim_records_provider_and_preserves_budget(target: Any) -> None:
    instance, shim = target
    fixture = FixtureModel()

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        schema = body["tools"][0]["function"]["parameters"]
        payload = json.loads(body["messages"][1]["content"][0]["text"])
        purpose = "intake" if "plan" in schema["properties"] else "synthesis"
        result = fixture.generate(system="合成 HTTP", payload=payload, schema=schema, purpose=purpose)
        return httpx.Response(
            200,
            content=recording(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "submit-" + purpose,
                                        "function": {"name": "submit", "arguments": json.dumps(result["output"])},
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            ),
        )

    shim.port = shim.registry.port(factory=lambda _: adapter(respond, max_retries=0))
    observed = instance.send({"user": "请陪我整理今天一个小行动。", "_index": 1})
    assert observed.error is None and observed.text and observed.model_calls == 2
    run = instance.repo.fetch_run(instance.owner, instance.run_ids[0])
    assert (run["status"], run["calls"], run["call_limit"]) == ("succeeded", 2, 6)
    records = instance.repo.list(instance.owner, "model_call")
    assert len(records) == 2 and {row["provider"] for row in records} == {"synthetic"}


def test_from_base_opt_in_and_rollback_select_concrete_models(target: Any, monkeypatch: Any) -> None:
    instance, _ = target
    monkeypatch.setenv("ZHIMING_DATABASE_URL", instance.dsn)
    monkeypatch.delenv("MODELS_CONFIG", raising=False)
    with patch("mingjing_core.application.consultation.PostgresRepository", return_value=instance.repo):
        monkeypatch.setenv("MINGJING_MODEL_PORT", "v2")
        assert isinstance(ConsultationService.from_base().model, PortBackedModel)
        monkeypatch.delenv("MINGJING_MODEL_PORT")
        assert isinstance(ConsultationService.from_base().model, ConfiguredModel)


def test_real_service_quota_failure_is_one_charge_and_no_repair(target: Any) -> None:
    instance, shim = target
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, text="synthetic quota")

    shim.port = shim.registry.port(
        factory=lambda _: adapter(respond, settings={"membership": True}, max_retries=0), stop_on_quota=True
    )
    instance.service.model = shim
    request = instance.service.submit(
        owner=instance.owner, message="合成额度保护验收", request_id="synthetic-port-quota"
    )
    instance.run_ids.append(request["id"])
    with pytest.raises(ModelQuotaExhausted):
        instance.service.execute(instance.owner, request["id"])
    run = instance.repo.fetch_run(instance.owner, request["id"])
    assert len(requests) == 1
    assert run["calls"] == 1 and run["status"] == "failed" and not run["repair_used"]
