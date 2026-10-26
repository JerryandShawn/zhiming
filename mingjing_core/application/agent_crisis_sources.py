"""Crisis detection uses authorized originals from this turn, never unrelated history."""

from mingjing_core.application.agent_tools_policy import source_policy
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError


def turn_sources(repo, run, identifiers=None):
    identifiers = identifiers or run["request"].get("source_message_ids", [run["request"]["source_message_id"]])
    if not 1 <= len(identifiers) <= 100 or len(set(identifiers)) != len(identifiers):
        raise EvidenceError("危机判定的本轮原话范围无效")
    memory, rows = MemoryService(repo), []
    thread = run.get("thread_id") or run["request"].get("thread_id") or "life:" + run["subject"]
    for ident in identifiers:
        row = memory.get_source(run["owner"], ident)
        projected = memory.get_source(run["owner"], ident, for_context=True)
        source_policy(row, run["subject"], thread)
        if row["content"] != projected["content"] or repo.is_revoked(run["owner"], "message", ident):
            raise EvidenceError("危机判定原话已改变或撤销")
        rows.append(row)
    return rows
