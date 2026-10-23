"""Safe provider errors; never retain request, response, key or transport cause."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mingjing_core.domain.consultation import ModelUnavailable as LegacyUnavailable

from .error_actions import ErrorActions, actions_for_kind
from .provider_diagnostics import ERROR_TYPES, QUOTA_SUBTYPES, public_quota_message


class ModelUnavailable(LegacyUnavailable):
    """A transient provider failure, compatible with v3 failure handling."""

    code = "MODEL_UNAVAILABLE"
    default_kind = "unavailable"
    allowed_kinds = frozenset({"unavailable"})

    def __init__(
        self,
        _message: str | None = None,
        *,
        status: int | None = None,
        error_type: str | None = None,
        provider_message: str | None = None,
        kind: str | None = None,
        retry_actions: ErrorActions | None = None,
    ) -> None:
        super().__init__(
            "模型服务暂时不可用，请恢复原请求",
            reason="http" if status else "network",
            provider_http_status=status,
        )
        self.provider_error_type = error_type if isinstance(error_type, str) and error_type in ERROR_TYPES else None
        self.provider_message = public_quota_message(provider_message)
        self.kind = kind if isinstance(kind, str) and kind in self.allowed_kinds else self.default_kind
        self.retry_actions = retry_actions if isinstance(retry_actions, ErrorActions) else actions_for_kind(self.kind)
        self.provider_reset_at: datetime | None = None

    @property
    def global_stop(self) -> bool:
        return self.retry_actions.global_stop

    def safe_diagnostic(self) -> dict[str, Any]:
        result = super().safe_diagnostic()
        result["kind"] = self.kind
        for name in ("provider_error_type", "provider_message", "quota_subtype"):
            value = getattr(self, name, None)
            if value is not None:
                result[name] = value
        if self.provider_http_status is not None:
            result["http_status"] = self.provider_http_status
        if self.provider_reset_at is not None:
            result["resume_at"] = self.provider_reset_at.isoformat()
        return result


class ModelRateLimited(ModelUnavailable):
    code = "MODEL_RATE_LIMITED"
    default_kind = "rate_limited"
    allowed_kinds = frozenset({"rate_limited", "engine_overloaded"})


class ModelQuotaExhausted(ModelUnavailable):
    code = "MODEL_QUOTA_EXHAUSTED"
    default_kind = "quota"
    allowed_kinds = QUOTA_SUBTYPES

    def __init__(
        self,
        _message: str | None = None,
        *,
        status: int | None = None,
        subtype: str = "quota",
        error_type: str | None = None,
        provider_message: str | None = None,
        kind: str | None = None,
        retry_actions: ErrorActions | None = None,
    ) -> None:
        if kind is not None and subtype != "quota" and kind != subtype:
            raise ValueError("Conflicting model error classification")
        selected = kind if kind is not None else subtype
        super().__init__(
            status=status,
            error_type=error_type,
            provider_message=provider_message,
            kind=selected,
            retry_actions=retry_actions,
        )
        self.quota_subtype = self.kind
        self.args = ("明镜的大脑今天有点累，额度恢复时间请查看会员控制台",)


class ModelBadRequest(ModelUnavailable):
    code = "MODEL_BAD_REQUEST"
    default_kind = "bad_request"
    allowed_kinds = frozenset({"bad_request", "reasoning_missing", "token_limit"})


class ModelPermissionDenied(ModelBadRequest):
    code = "MODEL_PERMISSION_DENIED"
    default_kind = "permission_error"
    allowed_kinds = frozenset({"permission_error", "access_terminated"})


# Both public names must identify the same class for existing exception handlers.
ModelPermissionError = ModelPermissionDenied


class ModelConcurrencyLimited(ModelPermissionDenied):
    code = "MODEL_CONCURRENCY_LIMITED"
    default_kind = "concurrency_limited"
    allowed_kinds = frozenset({"concurrency_limited"})


class ModelMembershipUnverified(ModelUnavailable):
    code = "MODEL_MEMBERSHIP_UNVERIFIED"
    default_kind = "membership_unverified"
    allowed_kinds = frozenset({"membership_unverified"})


class ModelContentFiltered(ModelBadRequest):
    code = "MODEL_CONTENT_FILTERED"
    default_kind = "content_filtered"
    allowed_kinds = frozenset({"content_filtered"})


class ModelPayloadTooLarge(ModelBadRequest):
    code = "MODEL_PAYLOAD_TOO_LARGE"
    default_kind = "payload_too_large"
    allowed_kinds = frozenset({"payload_too_large"})


class ModelCancelled(ModelUnavailable):
    code = "MODEL_CANCELLED"
    default_kind = "cancelled"
    allowed_kinds = frozenset({"cancelled"})

    def __init__(self, _message: str | None = None) -> None:
        super().__init__()
        self.args = ("本次模型调用已取消",)


class CapabilityError(ModelBadRequest):
    code = "MODEL_CAPABILITY_ERROR"
    default_kind = "capability_error"
    allowed_kinds = frozenset({"capability_error"})


class ModelProtocolError(ModelUnavailable):
    code = "MODEL_PROTOCOL_ERROR"
    default_kind = "protocol_error"
    allowed_kinds = frozenset({"protocol_error"})

    def __init__(self, _message: str | None = None, *, status: int | None = None) -> None:
        super().__init__(status=status)
        self.reason = "json"
        self.failure_code = "MODEL_JSON"
