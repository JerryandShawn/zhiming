"""Only a sealed, verified core session may select the two approved K3 identities."""

from __future__ import annotations

from dataclasses import replace

from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.quota_delegated_session import require_active
from mingjing_core.models.quota_mode import current_delegated_session
from mingjing_core.models.quota_r16 import K31CoreApproval, approved_core_model
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.models.registry import ModelHandle, ModelRegistry


def selected_model() -> str:
    session = require_active()
    if session.phase != "core":
        raise GuardRejected("manual_start_required")
    return approved_core_model(session.approval, session.guard.clock.now())


class ProofSelectedRegistry(ModelRegistry):
    @property
    def input_factor(self) -> str:
        if current_delegated_session() is None:
            return "1.15"
        session = require_active()
        return (
            session.approval.factor
            if isinstance(session.approval, K31CoreApproval)
            else "1.15"
        )

    def resolve(self, role: str = "primary") -> list[ModelHandle]:
        handles = super().resolve(role)
        # Construction outside an approved core scope retains the original
        # config. The tracking port still refuses all ungated eval requests.
        if current_delegated_session() is None:
            return handles
        model = selected_model()
        primary, critic = super().resolve("primary"), super().resolve("critic")
        configured = primary + critic
        if (
            role not in {"primary", "critic"}
            or not handles
            or not primary
            or not critic
            or any(
                handle.model
                not in ({"k3.1-pro"} if model == "k3.1-pro" else {"k3", "k3-256k"})
                or handle.model != configured[0].model
                or handle.settings.get("model_lock") != handle.model
                or handle.provider != "kimi_code"
                or handle.settings.get("membership") is not True
                or handle.settings.get("effort") != "high"
                or model == "k3.1-pro"
                and (
                    handle.settings.get("reasoning_effort") != "high"
                    or handle.protocol != "openai_compat"
                    or handle.base_url.rstrip("/") != "https://api.kimi.com/coding/v1"
                )
                or handle.caps.get("tools") is not True
                for handle in configured
            )
        ):
            raise ConfigError(
                "可信模型选择须绑定对应批准的会员配置、固定协议与高思考强度"
            )
        return [
            replace(
                handle, model=model, settings={**handle.settings, "model_lock": model}
            )
            for handle in handles
        ]
