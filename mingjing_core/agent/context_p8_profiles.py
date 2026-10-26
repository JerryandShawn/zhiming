"""Historical chart summaries require native completed work and current lineage."""

from __future__ import annotations

from psycopg import sql

from mingjing_core.adapters.charts.p8_worker import source_hashes
from mingjing_core.application.charts_documents import verify_p8_document
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import fingerprint

from .context_entities import _valid
from .p8_profile_text import profile_text


def _document(sources, owner, subject, step, *, profile_only=False):
    output = step["output"]
    data = output["data"]
    if data.get("adapter_mode") != "p8_v1_1" or data.get("tool_name"):
        return None
    operation = f"run:{step['run_id']}:e{step['epoch']}:s{step['seq']}"
    cache_id = "agent_chart_cache_" + fingerprint([owner, operation])[:32]
    cache = sources.repo.get(owner, "runtime_step", cache_id)
    if (
        cache["status"] != "active"
        or cache["subject_id"] != subject
        or cache.get("run_id") != step["run_id"]
        or type(cache.get("epoch")) is not int
        or cache.get("epoch") != step["epoch"]
        or cache.get("input_fp") != step["input_fp"]
        or fingerprint(cache.get("tool_output")) != fingerprint(output)
        or not sources.repo.verify_versions(
            owner, profile_versions(cache["snapshot"]) if profile_only else cache["snapshot"]["versions"]
        )
        or sources.repo.is_revoked(owner, "runtime_step", cache_id)
    ):
        return None
    docs = data["documents"]
    if len(docs) != 1 or docs[0]["kind"] != "time_basis":
        return None
    doc = docs[0]
    checked = verify_p8_document(
        doc["payload"],
        kind="time_basis",
        owner=owner,
        subject=subject,
        revision=cache["snapshot"]["revision"],
        operation_id=operation,
        source_sha256=source_hashes(),
    )
    if fingerprint(checked) != fingerprint(doc):
        return None
    return _archive(sources, owner, subject, step, cache, doc, operation)


def profile_versions(snapshot):
    """A displayed birth boundary does not depend on unrelated case/background facts."""
    return {
        key: value
        for key, value in snapshot["versions"].items()
        if key.startswith(("owner:", "subject:", "fact:", "message:"))
    }


def _archive(sources, owner, subject, step, cache, doc, operation):
    data = step["output"]["data"]
    ident = "agent_p8_" + fingerprint([owner, operation, doc["document_id"]])[:32]
    row = sources.repo.get(owner, "artifact", ident)
    record = {"id": ident, "revision": row["revision"], "document_id": doc["document_id"]}
    expected = dict(
        p8_document=doc,
        run_id=step["run_id"],
        epoch=step["epoch"],
        source_versions=cache["snapshot"]["versions"],
        source_ids=cache["snapshot"]["source_ids"],
        used_fact_ids=[fact["id"] for fact in cache["snapshot"]["facts"]],
        source_refs=[ref for fact in cache["snapshot"]["facts"] for ref in fact.get("source_refs", [])],
    )
    if (
        row["status"] != "active"
        or row["subject_id"] != subject
        or fingerprint(data["persisted"]["documents"]) != fingerprint([record])
        or type(record["revision"]) is not int
        or sources.repo.is_revoked(owner, "artifact", ident)
        or any(fingerprint(row.get(key)) != fingerprint(value) for key, value in expected.items())
    ):
        return None
    return row, cache, doc


def read_chart_profiles(sources, owner, subject, cases, facts):
    repo = sources.repo
    with repo.transaction(owner) as connection:
        steps = connection.execute(
            sql.SQL(
                "SELECT s.* FROM {} s JOIN {} r ON r.owner=s.owner AND r.id=s.run_id "
                "WHERE r.owner=%s AND r.subject=%s AND r.runtime='v4' AND r.status='succeeded' "
                "AND r.cancel_requested_at IS NULL AND r.thread_id=%s AND s.epoch=r.retry_epoch "
                "AND s.kind='tool' AND s.name='chart_compute' AND s.status='completed' "
                "AND s.error_code IS NULL AND s.finished_at IS NOT NULL AND s.output->>'ok'='true' "
                "ORDER BY s.finished_at DESC,s.seq DESC LIMIT 8"
            ).format(repo.table("core_run_steps"), repo.table("core_runs")),
            (owner, subject, "life:" + subject),
        ).fetchall()
        for step in steps:
            try:
                checked = _document(sources, owner, subject, step)
                if checked is None:
                    continue
                row, cache, doc = checked
                row = dict(row, entity_kind="artifact")
                if not _valid(sources, owner, subject, row, {fact["id"] for fact in facts}):
                    continue
                if any(
                    set(sources._source(owner, ident).get("case_ids", [])) - set(cases) for ident in row["source_ids"]
                ):
                    continue
                text = profile_text(doc, row["revision"])
                if text is None:
                    continue
                row.update(
                    _p8_profile_text=text,
                    profile_dependency_ids=[cache["id"]],
                )
                versions = {
                    key: value
                    for key, value in cache["snapshot"]["versions"].items()
                    if key.startswith(("fact:", "message:"))
                }
                versions[entity_dependency("runtime_step", cache["id"])] = cache["revision"]
                return (row,), versions
            except (CoreError, KeyError, TypeError, ValueError):
                # Invalid or unsupported archives are optional context, never repaired or re-created.
                continue
    return (), {}
