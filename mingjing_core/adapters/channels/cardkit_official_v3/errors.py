"""Pure error mapping from design 26; never infer delivery from a frequency refusal."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from .contracts import OfficialOutcome

# 已核实（26转录）：https://open.feishu.cn/document/cardkit-v1/card-element/content (2025-08-22).
REJECTED = frozenset({10002, 200740, 200750, 200860, 300302, 300311})
RETRYABLE = frozenset({200810, 200850, 300309, 300317})
UNKNOWN = frozenset({200770, 300120})


def _delay(headers: Mapping[str, str] | None) -> int:
    values = {key.lower(): value for key, value in (headers or {}).items() if type(key) is str}
    try:
        seconds = Decimal(str(values.get("x-ogw-ratelimit-reset", "1")))
        if not seconds.is_finite() or seconds < 0 or seconds > 86_400:
            return 1000
        return int((seconds * 1000).to_integral_value(rounding="ROUND_CEILING"))
    except (ValueError, InvalidOperation):
        return 1000


def classify_response(
    http_status: int | None, code: int | None, headers: Mapping[str, str] | None = None, *, network_error: bool = False
) -> OfficialOutcome:
    # 已核实（26转录）：https://open.feishu.cn/document/server-docs/api-call-guide/frequency-control (2024-10-10).
    if network_error or type(http_status) is not int or http_status >= 500:
        return OfficialOutcome("uncertain", "transport_or_unclassified_response")
    if http_status == 429 or (type(code) is int and code == 99991400):
        return OfficialOutcome("retryable", "rate_limited", _delay(headers))
    if type(code) is not int:
        return OfficialOutcome("uncertain", "transport_or_unclassified_response")
    if code in UNKNOWN:
        return OfficialOutcome("uncertain", "uuid_conflict" if code == 200770 else "remote_internal_error")
    if code in RETRYABLE:
        action = "reopen_or_finalize" if code in {200850, 300309} else None
        return OfficialOutcome("retryable", f"cardkit_{code}", 400, action)
    if code in REJECTED:
        return OfficialOutcome("rejected", f"cardkit_{code}")
    return OfficialOutcome("uncertain", "unclassified_response")
