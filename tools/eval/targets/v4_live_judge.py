"""The external evaluation judge uses a locked critic port and physical-call accounting."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from mingjing_core.models.legacy import PortBackedModel
from mingjing_core.models.port import ModelPort
from mingjing_core.models.registry import ModelHandle, ModelRegistry
from tools.eval.judges import ModelJudge
from tools.eval.quota import ProviderStopped, QuotaGuard

from .v4_live_ports import LiveTrackingPort


class LiveJudgeProvider(QuotaGuard):
    def __init__(
        self,
        model: str,
        *,
        environment: Mapping[str, str] | None = None,
        adapter_factory: Callable[[ModelHandle], ModelPort] | None = None,
    ) -> None:
        registry = ModelRegistry(environment=environment)
        handles = registry.resolve("critic")
        if not handles or any(
            handle.model != model
            or handle.settings.get("model_lock") != model
            or handle.settings.get("effort") != "high"
            or handle.settings.get("membership") is not True
            for handle in handles
        ):
            raise ValueError("Live judge differs from the locked membership critic configuration")
        provider = PortBackedModel(registry, role="critic", stop_on_quota=True)
        if adapter_factory is not None:
            provider.port.factory = adapter_factory
        self.tracker = LiveTrackingPort(provider.port, role="judge")
        provider.port = self.tracker
        super().__init__(provider, "judge")

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.check_open()
        started = time.perf_counter()
        self.tracker.begin_turn()
        try:
            return self.provider.generate(**kwargs)
        except ProviderStopped as error:
            self.stop_reason, self.provider_http_status = error.reason, error.provider_http_status
            raise
        finally:
            self.calls = self.tracker.calls
            self.elapsed_seconds += time.perf_counter() - started


class V4LiveJudge(ModelJudge):
    def __init__(
        self,
        model: str,
        rubric: Path,
        *,
        environment: Mapping[str, str] | None = None,
        adapter_factory: Callable[[ModelHandle], ModelPort] | None = None,
    ) -> None:
        super().__init__(
            model, rubric, LiveJudgeProvider(model, environment=environment, adapter_factory=adapter_factory)
        )
