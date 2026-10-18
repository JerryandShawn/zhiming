"""One pure HTTP/SSE classification boundary; no raw error text is retained."""

from __future__ import annotations

import re
from typing import Literal

from .error_actions import NEVER, PROVIDER_QUOTA
from .errors import (
    ModelBadRequest,
    ModelConcurrencyLimited,
    ModelContentFiltered,
    ModelMembershipUnverified,
    ModelPayloadTooLarge,
    ModelPermissionError,
    ModelQuotaExhausted,
    ModelRateLimited,
    ModelUnavailable,
)
from .provider_diagnostics import nested_error_fields, permission_quota

_CONCURRENT = re.compile(
    r"\bconcurrent\b|\bconcurrency(?:_limited)?\b|并发(?:请求)?(?:受限|限制)|达到.{0,12}并发", re.I
)
_ACCESS = re.compile(r"^\s*access\s+terminated\b", re.I)
_MEMBERSHIP = re.compile(
    r"(?:unable|cannot|failed).{0,16}verify.{0,30}membership|membership verification failed|无法验证会员|会员验证失败",
    re.I,
)


def _valid_status(status: object) -> int | None:
    return status if type(status) is int and 400 <= status <= 599 else None


def _permission(status: int | None, payload: object, membership: bool) -> ModelUnavailable:
    error_type, message = nested_error_fields(payload)
    if match := permission_quota(payload):
        subtype, public = match
        return ModelQuotaExhausted(
            status=status,
            subtype=subtype,
            error_type=error_type,
            provider_message=public,
            retry_actions=None if membership else PROVIDER_QUOTA,
        )
    if membership and (
        error_type == "concurrency_limited" or error_type == "permission_error" and _CONCURRENT.search(message)
    ):
        return ModelConcurrencyLimited(status=status, error_type=error_type)
    return ModelPermissionError(status=status, error_type=error_type)


def _bad_request(status: int | None, error_type: str | None, message: str) -> ModelUnavailable:
    lowered = message.casefold()
    if "reasoning_content" in lowered and re.search(r"missing|absent|缺失|缺少", lowered):
        return ModelBadRequest(status=status, error_type=error_type, kind="reasoning_missing")
    if re.search(r"(?:total message size|消息.{0,4}(?:大小|体积)).{0,40}(?:exceed|超过|超出)", lowered):
        return ModelPayloadTooLarge(status=status, error_type=error_type)
    if "token" in lowered and re.search(r"limit|上限", lowered) and re.search(r"exceed|超过|超出", lowered):
        return ModelBadRequest(status=status, error_type=error_type, kind="token_limit")
    if re.search(r"high risk|content safety|内容安全", lowered) and re.search(r"reject|拒绝|拦截", lowered):
        return ModelContentFiltered(status=status, error_type=error_type)
    return ModelBadRequest(status=status, error_type=error_type)


def _rate_limit(status: int | None, error_type: str | None, message: str) -> ModelRateLimited:
    overloaded = error_type == "overloaded_error" or re.search(r"overload|过载", message, re.I)
    return ModelRateLimited(
        status=status, error_type=error_type, kind="engine_overloaded" if overloaded else "rate_limited"
    )


def _http_error(status: int | None, payload: object, membership: bool) -> ModelUnavailable:
    error_type, message = nested_error_fields(payload)
    if status == 403:
        return _permission(status, payload, membership)
    if status == 402:
        if membership:
            return ModelMembershipUnverified(status=status, error_type=error_type)
        return ModelBadRequest(status=status, error_type=error_type)
    if status == 429:
        return _rate_limit(status, error_type, message)
    if status == 400:
        return _bad_request(status, error_type, message)
    if status is not None and status >= 500:
        return ModelUnavailable(status=status, error_type=error_type)
    if status is not None:
        return ModelBadRequest(status=status, error_type=error_type)
    return ModelUnavailable(error_type=error_type, retry_actions=NEVER)


def _stream_error(payload: object, membership: bool) -> ModelUnavailable:
    error_type, message = nested_error_fields(payload)
    if error_type in {"permission_error", "concurrency_limited"}:
        return _permission(None, payload, membership)
    if error_type == "billing_error" and _MEMBERSHIP.search(message):
        return ModelMembershipUnverified(error_type=error_type)
    if error_type in {"rate_limit_error", "overloaded_error"}:
        return _rate_limit(None, error_type, message)
    if error_type == "invalid_request_error":
        return _bad_request(None, error_type, message)
    return ModelUnavailable(error_type=error_type, retry_actions=None if error_type == "api_error" else NEVER)


def classify_error(
    status: int | None,
    payload: object,
    *,
    membership: bool,
    surface: Literal["http", "sse"] = "http",
) -> ModelUnavailable:
    error_type, message = nested_error_fields(payload)
    status = _valid_status(status)
    # D1 takes precedence even when the provider uses a different error status.
    if membership and error_type and (error_type == "access_terminated" or _ACCESS.search(message)):
        return ModelPermissionError(status=status, error_type=error_type, kind="access_terminated")
    if membership and error_type == "concurrency_limited":
        return ModelConcurrencyLimited(status=status, error_type=error_type)
    if not membership and error_type == "insufficient_quota" and (status == 429 or surface == "sse" and status is None):
        return ModelQuotaExhausted(status=status, error_type=error_type, retry_actions=PROVIDER_QUOTA)
    if surface == "http" or status is not None:
        return _http_error(status, payload, membership)
    return _stream_error(payload, membership)
