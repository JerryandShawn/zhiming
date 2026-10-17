"""The night quota circuit must stop before any sibling model is called."""

import json
from dataclasses import replace
from typing import Any
from unittest.mock import patch

import httpx

from mingjing_core.models.registry import ModelHandle
from tools import probe_models
from tools.model_probe_cases import cases


def handle() -> Any:
    return ModelHandle(
        "kimi-code-main",
        "kimi_code",
        "k3",
        "anthropic_messages",
        "https://api.kimi.com/coding/v1",
        "synthetic-key",
        {},
        {"membership": True},
    )


def test_probe_quota_is_one_actual_request_and_no_body_in_result() -> None:
    original = ModelHandle.adapter

    def factory(instance: Any, **kwargs: Any) -> Any:
        return original(
            instance, transport=httpx.MockTransport(lambda _: httpx.Response(429, text="private quota")), **kwargs
        )

    with patch.object(ModelHandle, "adapter", factory):
        row = probe_models._run(handle(), cases()[0])
    assert row["quota"] and row["calls"] == 1
    assert "private" not in json.dumps(row)


def test_probe_main_stops_global_after_first_quota(tmp_path: Any) -> None:
    class Registry:
        path = tmp_path / "models.yaml"

        def resolve(self, role: Any) -> Any:
            return [handle() if role == "primary" else replace(handle(), model="k3-256k")]

    calls = []

    def run(item: Any, probe: Any) -> Any:
        calls.append(item.model)
        return {
            "model": item.model,
            "probe": probe.name,
            "protocol": item.protocol,
            "passed": False,
            "error_code": "MODEL_QUOTA_EXHAUSTED",
            "quota": True,
            "calls": 1,
        }

    stop = tmp_path / "quota.json"
    argv = ["probe_models", "--stop-file", str(stop), "--output", str(tmp_path / "probe")]
    with (
        patch("sys.argv", argv),
        patch.object(probe_models, "ModelRegistry", Registry),
        patch.object(probe_models, "_run", run),
    ):
        assert probe_models.main() == 2
    assert calls == ["k3"] and stop.exists()
    assert json.loads((tmp_path / "probe.json").read_text())["total_calls"] == 1
    with patch("sys.argv", argv):
        try:
            probe_models.main()
        except SystemExit as error:
            assert "no calls after" in str(error)
        else:
            raise AssertionError("quota stop must be permanent for the night")
