"""A trusted execution-stack callback transfers one reclaimed lease, never an SSE field."""

from __future__ import annotations

from typing import Any

from mingjing_core.domain.contracts import LeaseConflict


class DispatcherServiceProxy:
    def __init__(self, service: Any, run: dict[str, Any]) -> None:
        self.service, self.run = service, dict(run)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.service, name)

    def agent_lease_changed(self, old_run: dict[str, Any], new_run: dict[str, Any]) -> None:
        keys = ("owner", "id", "subject", "runtime", "retry_epoch", "lease_token")
        if any(old_run.get(key) != self.run.get(key) for key in keys) or old_run["retry_epoch"] != 0:
            raise LeaseConflict("租约移交缺少本次执行的原始凭据")
        if (
            any(new_run.get(key) != old_run.get(key) for key in ("owner", "id", "subject", "runtime"))
            or new_run.get("runtime") != "v4"
            or new_run.get("retry_epoch") != 1
            or not new_run.get("lease_token")
            or new_run["lease_token"] == old_run["lease_token"]
        ):
            raise LeaseConflict("租约移交人物、运行或批次不符")
        with self.repo.transaction(old_run["owner"]) as connection:
            current = self.repo._run(
                self.repo._leased(connection, new_run["owner"], new_run["id"], new_run["lease_token"])
            )
            if any(current.get(key) != new_run.get(key) for key in keys):
                raise LeaseConflict("租约移交与持久权威不符")
            self.run = current
        hook = getattr(self.service, "agent_lease_changed", None)
        if hook is not None:
            hook(old_run, self.run)
