"""Explicit process configuration installs dependencies without making model calls."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.release_switches import load_switches
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.registry import ModelRegistry

ENABLED_ENV = "MINGJING_AGENT_ENABLED"
ARTIFACT_ENV = "K3_TOKENIZER_DIR"


def configured_agent(
    repo: Any,
    *,
    environment: Mapping[str, str] | None = None,
    registry_factory: Callable[..., ModelRegistry] = ModelRegistry,
) -> AgentRuntime | None:
    source = os.environ if environment is None else environment
    enabled = source.get(ENABLED_ENV, "false")
    if enabled == "false":
        return None
    if enabled != "true":
        raise EvidenceError("Agent 开关仅接受 true 或 false")
    if type(repo.max_running) is not int or repo.max_running < 3:
        raise EvidenceError("Agent 启动需要明确配置三条运行容量")
    directory = source.get(ARTIFACT_ENV, "")
    if not directory or not Path(directory).is_absolute():
        raise EvidenceError("Agent 启动缺少固定的本地分词器目录")
    return _build(repo, source, Path(directory), registry_factory)


def _build(
    repo: Any, source: Mapping[str, str], directory: Path, registry_factory: Callable[..., ModelRegistry]
) -> AgentRuntime:
    from mingjing_core.agent.k3_loader import load_k3_counter
    from mingjing_core.models.quota_runtime import CentralLocation

    # Constructor verification checks the deployed account, UUID and actual PG
    # location. It neither provisions an account nor reserves a physical attempt.
    CentralLocation.from_environment(source).guard()
    registry = registry_factory(environment=source)
    handles = registry.resolve("primary")
    if not handles or any(
        handle.model != handles[0].model
        or handle.settings.get("model_lock") != handle.model
        or handle.settings.get("effort") != "high"
        or handle.settings.get("membership") is not True
        or handle.caps.get("tools") is not True
        for handle in handles
    ):
        raise EvidenceError("Agent 主模型须由配置锁定同一会员模型、工具与高思考强度")
    meter = K3EstimatedMeter(
        load_k3_counter(directory), model=handles[0].model, factor=getattr(registry, "input_factor", "1.15")
    )
    if not meter.live_admissible:
        raise EvidenceError("Agent 分词计量尚未核验")
    # Release switches come only from the checked-in config/switches.yaml. The
    # critic port is built only when review is on, so `off` makes no critic request.
    switches = load_switches()
    critic = registry.port("critic") if switches.review_mode != "off" else None
    return AgentRuntime(
        repo,
        registry.port("primary", stop_on_quota=True),
        meter,
        critic=critic,
        offline=False,
        streaming_candidate=switches.streaming_v2,
        review_mode=switches.review_mode,
    )
