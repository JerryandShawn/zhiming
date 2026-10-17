"""Evaluation-only stop signals bypass business repair without exposing provider text."""

import re
import time
from typing import Any


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
    ) -> None:
        super().__init__("Evaluation provider stopped; an explicit user decision is required")
        self.reason = reason
        self.role = role
        self.elapsed_seconds = elapsed_seconds
        self.model_calls = model_calls
        self.provider_http_status = (
            provider_http_status if type(provider_http_status) is int and 100 <= provider_http_status <= 599 else None
        )


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
    status = provider_http_status(exc)
    if status == 429 or re.search(r"quota|usage[\s_-]*limit|rate[\s_-]*limit|额度|限额", str(exc).casefold()):
        return "quota"
    return "provider_http_error" if type(status) is int and 100 <= status <= 599 and status != 200 else None


class QuotaGuard:
    """Meter actual provider calls and permanently open the circuit after a stop."""

    def __init__(self, provider: Any, role: str) -> None:
        self.provider = provider
        self.role = role
        self.calls = 0
        self.elapsed_seconds = 0.0
        self.stop_reason: str | None = None
        self.provider_http_status: int | None = None

    def check_open(self) -> None:
        if self.stop_reason:
            raise ProviderStopped(self.stop_reason, self.role, provider_http_status=self.provider_http_status)

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.check_open()
        self.calls += 1
        started = time.perf_counter()
        try:
            return self.provider.generate(**kwargs)
        except Exception as exc:
            reason = provider_stop_reason(exc)
            if reason:
                self.stop_reason = reason
                self.provider_http_status = provider_http_status(exc)
                raise ProviderStopped(
                    reason,
                    self.role,
                    elapsed_seconds=time.perf_counter() - started,
                    model_calls=1,
                    provider_http_status=self.provider_http_status,
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
