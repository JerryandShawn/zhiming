"""Central accounting and current K3 policy for the retained single-submit adapter."""

from __future__ import annotations

from typing import Any

import httpx

from .error_classification import classify_error
from .legacy_request_policy import member_body
from .metering import before_provider_request
from .provider_diagnostics import delegated_stop_hint
from .provider_reset import attach_reset
from .quota_guard import QuotaGuard
from .quota_http import membership_endpoint, observe_usage, provider_attempt
from .quota_mode import delegated_active
from .request_policy import check_request_size


def post_legacy(
    client: httpx.Client,
    *,
    base: str,
    model: str,
    role: str,
    headers: dict[str, str],
    body: dict[str, Any],
    guard: QuotaGuard | None = None,
) -> httpx.Response:
    membership = guard is not None or membership_endpoint(base) or model.strip().casefold().startswith("k3")
    if not membership:
        before_provider_request()
        return client.post(base + "/messages", headers=headers, json=body)
    normalized = member_body(body, model=model, role=role)
    request = client.build_request("POST", base + "/messages", headers=headers, json=normalized)
    check_request_size(request, model=model, settings={})
    transport = getattr(client, "_transport", None)
    with provider_attempt(
        membership=True,
        role=role,
        provider="kimi_code",
        model=model,
        transport=transport,
        guard=guard,
    ) as attempt:
        before_provider_request()
        response = client.send(request)
        parsed = None
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        if response.status_code != 200:
            observed = delegated_stop_hint(response.text[:4096]) if delegated_active() else None
            raise attach_reset(
                classify_error(
                    response.status_code,
                    parsed,
                    membership=True,
                    observed_stop=observed,
                ),
                response.headers,
            )
        if isinstance(parsed, dict):
            usage = parsed.get("usage")
            if isinstance(usage, dict):
                observe_usage(attempt, usage)
        return response
