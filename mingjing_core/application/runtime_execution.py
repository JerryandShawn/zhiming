"""Direct service calls retain the private clean-epoch lease handoff just like workers."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_service import DispatcherServiceProxy
from mingjing_core.domain.contracts import RevisionConflict


def execute_agent(service: Any, run: dict[str, Any], emit: Any = None) -> dict[str, Any]:
    proxy = DispatcherServiceProxy(service, run)
    owner, ident = run["owner"], run["id"]
    try:
        return service.runtime_assembly.execute(proxy, owner, ident, run["lease_token"], emit)
    except Exception as error:
        current = service.repo.fetch_run(owner, ident)
        if current["status"] == "succeeded":
            return current["result"]
        if current["status"] == "running" and current["lease_token"] == proxy.run["lease_token"]:
            if current["cancel_requested_at"]:
                DispatcherCancellation(service.repo).finish(proxy.run)
            else:
                service.repo.fail_run(
                    owner,
                    ident,
                    "本轮尚未完成，请恢复原请求",
                    proxy.run["lease_token"],
                    status="stale" if isinstance(error, RevisionConflict) else "failed",
                )
        raise
    finally:
        current = service.repo.fetch_run(owner, ident)
        if current["status"] == "revoked":
            for epoch in range(current["retry_epoch"] + 1):
                service.runtime.purge(ident, epoch)
