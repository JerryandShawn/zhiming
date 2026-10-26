"""Non-blocking, body-free boundary notice from completed native chart evidence."""

from copy import deepcopy

from psycopg import sql

from mingjing_core.agent.event_contracts import EnvelopeV1
from mingjing_core.agent.p8_boundary_guidance import boundary_guidance
from mingjing_core.application.agent_chart_lineage import chart_lineage
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.skills.boundary_messages import PILLARS

WORDS = ("临界", "分界", "交界", "换日", "交节", "交接", "小边界", "实现差值")
WARNING = {"code": "chart_inconsistency", "severity": 1}


def missing_notice(text, guidance):
    if any(word in text for word in WORDS):
        return False
    for item in guidance:
        if not any(PILLARS[key] in text for key in item["affected_pillars"]):
            continue
        if any(f"〔{alias}〕" in text for alias in [item["rule_alias"], *item["evidence_aliases"]]):
            return True
    return False


def native_guidance(repo, run, aliases):
    with repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='tool' AND name='chart_compute' AND status='completed' "
                "AND error_code IS NULL AND finished_at IS NOT NULL AND output->>'ok'='true' "
                "AND output->'data'->>'adapter_mode'='p8_v1_1' ORDER BY seq"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"]),
        ).fetchall()
        service, guidance = AgentToolsService(repo), []
        for row in rows:
            result = ToolResult.model_validate(row["output"])
            records, _ = chart_lineage(service, run, result)
            actual = {fingerprint(record) for record in records}
            trusted = {key: record for key, record in aliases.items() if fingerprint(record) in actual}
            guidance.extend(boundary_guidance(result.data, trusted))
        return guidance


def boundary_warning(repo, run, checked, aliases):
    # This optional lexical check never supplies a critic verdict or authorizes a citation.
    # The finalizer has already checked the lease, source, versions and critic proof.
    if any(word in checked.text for word in WORDS):
        return False
    try:
        guidance = native_guidance(repo, run, aliases)
    except (CoreError, ValueError, KeyError, TypeError):
        return False
    return missing_notice(checked.text, guidance)


def with_boundary_warning(envelope, warning):
    if not warning:
        return envelope
    value = deepcopy(envelope)
    if WARNING not in value["review"]["reasons"]:
        value["review"]["reasons"].append(dict(WARNING))
    return EnvelopeV1.model_validate(value).model_dump(by_alias=True, exclude_unset=True)
