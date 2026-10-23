"""Evaluation-only stop signals bypass business repair without exposing provider text."""

from __future__ import annotations

import re
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mingjing_core.models.errors import ModelUnavailable as TypedModelUnavailable
from mingjing_core.models.metering import request_meter
from mingjing_core.models.quota_runtime import call_scope, current_scope
from mingjing_core.models.quota_types import GuardRejected

if TYPE_CHECKING:
    from tools.eval.member_budget import MemberBudget

STOP_REASONS = (
    frozenset(
        {
            "quota",
            "quota_5h",
            "quota_weekly",
            "quota_monthly",
            "concurrency_limited",
            "access_terminated",
            "provider_http_error",
            "member_window_limit",
            "batch_cooldown",
        }
    )
    | GuardRejected.allowed_kinds
)


class ProviderStopped(BaseException):
    """A control signal; ordinary provider/critic exception handlers must not retry it."""

    def __init__(
        self,
        reason: str,
        role: str,
        *,
        elapsed_seconds: float = 0.0,
        model_calls: int = 0,
        provider_http_status: int | None = None,
        resume_at: str | None = None,
    ) -> None:
        super().__init__("Evaluation provider stopped before another request")
        self.reason = reason if reason in STOP_REASONS else "provider_http_error"
        self.subtype = self.reason
        self.role = role if role in {"target", "judge", "probe"} else "target"
        self.elapsed_seconds = elapsed_seconds
        self.model_calls = model_calls
        self.provider_http_status = (
            provider_http_status if type(provider_http_status) is int and 100 <= provider_http_status <= 599 else None
        )
        self.resume_at = _resume_at(resume_at)

    def safe_diagnostic(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "subtype": self.subtype,
            "role": self.role,
            "provider_http_status": self.provider_http_status,
            "resume_at": self.resume_at,
            "model_calls": self.model_calls,
        }


def _resume_at(value: str | None) -> str | None:
    try:
        stamp = datetime.fromisoformat(value or "")
        return stamp.astimezone(UTC).isoformat() if stamp.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def provider_http_status(exc: Exception) -> int | None:
    diagnostic = exc.safe_diagnostic() if callable(getattr(exc, "safe_diagnostic", None)) else {}
    status = diagnostic.get("provider_http_status") or getattr(exc, "provider_http_status", None)
    status = status or getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc).casefold()
    if status is None:
        match = re.search(r"(?:http(?:\s+status)?|status(?:_code)?)\s*[:=]?\s*(\d{3})\b", text)
        status = int(match[1]) if match else None
    if status is None and re.search(r"\b429\b", text):
        status = 429
    return status if type(status) is int and 100 <= status <= 599 else None


def provider_stop_reason(exc: Exception) -> str | None:
    if isinstance(exc, GuardRejected):
        return exc.kind
    if isinstance(exc, TypedModelUnavailable):
        if exc.kind in {
            "quota",
            "quota_5h",
            "quota_weekly",
            "quota_monthly",
            "concurrency_limited",
            "access_terminated",
        }:
            return exc.kind
        # The adapter has already exhausted its own retry policy. Never re-label rate as quota.
        return "provider_http_error"
    subtype = getattr(exc, "quota_subtype", None)
    if subtype in {"quota", "quota_5h", "quota_weekly"}:
        return subtype
    status = provider_http_status(exc)
    if status == 429 or re.search(r"quota|usage[\s_-]*limit|rate[\s_-]*limit|额度|限额", str(exc).casefold()):
        return "quota"
    return "provider_http_error" if type(status) is int and 100 <= status <= 599 and status != 200 else None


class QuotaGuard:
    """Open the circuit after a stop; only the persistent policy may reopen it."""

    def __init__(self, provider: Any, role: str, budget: MemberBudget | None = None) -> None:
        self.provider = provider
        self.role = role
        self.calls = 0
        self.elapsed_seconds = 0.0
        self.stop_reason: str | None = None
        self.provider_http_status: int | None = None
        self.budget = budget

    def check_open(self) -> None:
        if self.budget is not None:
            try:
                self.budget.check_open(self.role)
            except ProviderStopped as exc:
                self.stop_reason = exc.reason
                self.provider_http_status = exc.provider_http_status
                raise
            if self.stop_reason in {
                "quota_5h",
                "member_window_limit",
                "batch_cooldown",
            }:
                self.stop_reason = None
        if self.stop_reason:
            raise ProviderStopped(
                self.stop_reason,
                self.role,
                provider_http_status=self.provider_http_status,
            )

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.check_open()
        self.calls += 1
        started = time.perf_counter()
        try:
            callback = (lambda: self.budget.before_provider_request(self.role)) if self.budget is not None else None
            scope = replace(current_scope(), lane="probe" if self.role == "probe" else "eval")
            with request_meter(callback), call_scope(scope):
                return self.provider.generate(**kwargs)
        except ProviderStopped as exc:
            self.stop_reason = exc.reason
            self.provider_http_status = exc.provider_http_status
            raise
        except Exception as exc:
            reason = provider_stop_reason(exc)
            if reason:
                self.stop_reason = reason
                self.provider_http_status = provider_http_status(exc)
                if self.budget is not None:
                    self.budget.record_stop(reason, self.provider_http_status)
                raise ProviderStopped(
                    reason,
                    self.role,
                    elapsed_seconds=time.perf_counter() - started,
                    model_calls=1,
                    provider_http_status=self.provider_http_status,
                    resume_at=self.budget.snapshot().get("resume_at") if self.budget is not None else None,
                ) from None
            raise
        finally:
            self.elapsed_seconds += time.perf_counter() - started


def guard_judge(judge: Any) -> QuotaGuard | None:
    provider = getattr(judge, "provider", None)
    if provider is None:
        return None
    if not isinstance(provider, QuotaGuard):
        judge.provider = QuotaGuard(provider, "judge")
    return judge.provider
