"""Safe provider errors; never retain request, response, key or transport cause."""

from mingjing_core.domain.consultation import ModelUnavailable as LegacyUnavailable


class ModelUnavailable(LegacyUnavailable):
    """A transient provider failure, compatible with v3 failure handling."""

    code = "MODEL_UNAVAILABLE"

    def __init__(self, _message: str | None = None, *, status: int | None = None) -> None:
        super().__init__(
            "模型服务暂时不可用，请恢复原请求", reason="http" if status else "network", provider_http_status=status
        )


class ModelRateLimited(ModelUnavailable):
    code = "MODEL_RATE_LIMITED"


class ModelQuotaExhausted(ModelUnavailable):
    code = "MODEL_QUOTA_EXHAUSTED"

    def __init__(self, _message: str | None = None, *, status: int | None = None) -> None:
        super().__init__(status=status)
        self.args = ("明镜的大脑今天有点累，额度恢复时间请查看会员控制台",)


class ModelBadRequest(ModelUnavailable):
    code = "MODEL_BAD_REQUEST"


class ModelCancelled(ModelUnavailable):
    code = "MODEL_CANCELLED"

    def __init__(self, _message: str | None = None) -> None:
        super().__init__()
        self.args = ("本次模型调用已取消",)


class CapabilityError(ModelBadRequest):
    code = "MODEL_CAPABILITY_ERROR"


class ModelProtocolError(ModelUnavailable):
    code = "MODEL_PROTOCOL_ERROR"
