"""Safe provider errors; never retain request, response, key or transport cause."""

from typing import Any

from mingjing_core.domain.consultation import ModelUnavailable as LegacyUnavailable

from .provider_diagnostics import ERROR_TYPES, QUOTA_SUBTYPES, public_quota_message


class ModelUnavailable(LegacyUnavailable):
    """A transient provider failure, compatible with v3 failure handling."""

    code = "MODEL_UNAVAILABLE"

    def __init__(
        self,
        _message: str | None = None,
        *,
        status: int | None = None,
        error_type: str | None = None,
        provider_message: str | None = None,
    ) -> None:
        super().__init__(
            "模型服务暂时不可用，请恢复原请求",
            reason="http" if status else "network",
            provider_http_status=status,
        )
        self.provider_error_type = error_type if isinstance(error_type, str) and error_type in ERROR_TYPES else None
        self.provider_message = public_quota_message(provider_message)

    def safe_diagnostic(self) -> dict[str, Any]:
        result = super().safe_diagnostic()
        for name in ("provider_error_type", "provider_message", "quota_subtype"):
            value = getattr(self, name, None)
            if value is not None:
                result[name] = value
        if self.provider_http_status is not None:
            result["http_status"] = self.provider_http_status
        return result


class ModelRateLimited(ModelUnavailable):
    code = "MODEL_RATE_LIMITED"


class ModelQuotaExhausted(ModelUnavailable):
    code = "MODEL_QUOTA_EXHAUSTED"

    def __init__(
        self,
        _message: str | None = None,
        *,
        status: int | None = None,
        subtype: str = "quota",
        error_type: str | None = None,
        provider_message: str | None = None,
    ) -> None:
        super().__init__(status=status, error_type=error_type, provider_message=provider_message)
        self.quota_subtype = subtype if isinstance(subtype, str) and subtype in QUOTA_SUBTYPES else "quota"
        self.args = ("明镜的大脑今天有点累，额度恢复时间请查看会员控制台",)


class ModelBadRequest(ModelUnavailable):
    code = "MODEL_BAD_REQUEST"


class ModelPermissionDenied(ModelBadRequest):
    code = "MODEL_PERMISSION_DENIED"


class ModelCancelled(ModelUnavailable):
    code = "MODEL_CANCELLED"

    def __init__(self, _message: str | None = None) -> None:
        super().__init__()
        self.args = ("本次模型调用已取消",)


class CapabilityError(ModelBadRequest):
    code = "MODEL_CAPABILITY_ERROR"


class ModelProtocolError(ModelUnavailable):
    code = "MODEL_PROTOCOL_ERROR"

    def __init__(self, _message: str | None = None, *, status: int | None = None) -> None:
        super().__init__(status=status)
        self.reason = "json"
        self.failure_code = "MODEL_JSON"
