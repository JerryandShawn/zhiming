"""One persisted thread identity shared by context, tools and final publication."""

from collections.abc import Mapping
from typing import Any

from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository


def thread_id(run: Mapping[str, Any]) -> str:
    return run.get("thread_id") or run.get("request", {}).get("thread_id") or "life:" + run["subject"]


def assert_thread(repo: PostgresRepository, run: Mapping[str, Any]) -> str:
    ident = thread_id(run)
    private = ident.startswith("incognito:")
    if private != (run.get("request", {}).get("incognito") is True):
        raise EvidenceError("无痕线程标记与持久运行不符")
    if not private:
        if ident != "life:" + run["subject"]:
            raise ScopeError("人生线程不属于当前人物")
        return ident
    if run.get("request", {}).get("case_ids"):
        raise EvidenceError("无痕线程不能携带长期事项")
    ThreadService(repo).get(run["owner"], ident, subject=run["subject"])
    return ident
