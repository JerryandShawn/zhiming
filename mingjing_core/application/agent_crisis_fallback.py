"""No-provider crisis template also works when input metering cannot admit a request."""

from mingjing_core.agent.crisis import fallback_text
from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.application.agent_crisis_sources import turn_sources
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_runtime_state import RuntimeState
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError


def commit_unavailable_template(repo, supplied, events, *, reason: str):
    owner = supplied["owner"]
    state = RuntimeState(repo)
    with repo.transaction(owner):
        current = state.authority(owner, supplied["id"], supplied["lease_token"])
        source = MemoryService(repo).get_source(owner, current["request"]["source_message_id"], for_context=True)
        if (
            source["status"] != "active"
            or source.get("role") != "user"
            or source["subject_id"] != current["subject"]
            or source.get("content") != current["request"]["message"]
            or source.get("policy", {}).get("origin") != "current_user"
            or source.get("policy", {}).get("run_context") is not True
            or repo.is_revoked(owner, "message", source["id"])
        ):
            raise EvidenceError("危机兜底仍须有效的当前用户原话")
        versions = reconcile_versions(repo, current, current["state_version"])
        versions.update({"message:" + row["id"]: row["revision"] for row in turn_sources(repo, current)})
        revision = repo.assert_scope(owner, current["subject"])["revision"]
        repo.set_run_dependencies(owner, current["id"], versions, current["lease_token"])
        state.metadata(current, fallback="availability_template", fallback_reason=reason)
        envelope = AgentFinalizer(repo).finalize(
            current,
            text=fallback_text(),
            alias_map={},
            versions=versions,
            snapshot_revision=revision,
            usage={"model_steps": 0, "fallback": "availability_template"},
        )
    events.send("final", {"message_id": envelope["message_id"], "envelope": envelope})
    return envelope
