"""Write authority comes from queued originals and proven adopted inbox requests."""

from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.application.thread_sources import ingress_sources, source_segments
from mingjing_core.domain.contracts import EvidenceError, ScopeError


def current_source_ids(repo, run) -> tuple[str, ...]:
    request = run["request"]
    primary = request["source_message_id"]
    identifiers = request.get("source_message_ids")
    if identifiers is None:
        result = (primary,)
    else:
        rows = ingress_sources(repo, run["owner"], run["subject"], run["thread_id"], identifiers)
        if rows[-1]["id"] != primary or source_segments(rows) != request.get("source_segments"):
            raise EvidenceError("本轮可写来源与持久合并区间不符")
        result = tuple(row["id"] for row in rows)
    try:
        repo.get(run["owner"], "thread", run.get("thread_id") or "life:" + run["subject"])
    except ScopeError:
        return result
    adopted = ThreadInbox(repo).authorized_source_ids(run)
    combined = tuple(dict.fromkeys((*result, *adopted)))
    if len(combined) > 100:
        raise EvidenceError("本轮受信原话数量超过上限")
    return combined
