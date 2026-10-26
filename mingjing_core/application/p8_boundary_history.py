"""Proof of a full explanation comes from published native text, never a tool hint."""

from __future__ import annotations

import re

from psycopg import sql

from mingjing_core.agent.context_p8_profiles import _document, profile_versions
from mingjing_core.agent.envelope import validated_result
from mingjing_core.application.agent_chart_lineage import chart_cache
from mingjing_core.application.p8_reference_records import selected_references
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import fingerprint


def canonical(text: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"〔[cr][1-9][0-9]*〕", "", text))


def _profile(snapshot):
    return fingerprint(
        sorted((row["id"], row["revision"], row.get("field"), row.get("value")) for row in snapshot["facts"])
    )


def _references(service, owner, step, cache, doc, stored, publication):
    data, versions, kinds = step["output"]["data"], {}, set()
    operation = f"run:{step['run_id']}:e{step['epoch']}:s{step['seq']}"
    refs = selected_references(data["documents"], data["requested_system"], data["persisted"]["limit"])
    expected = {"artifacts": [], "claims": []}
    for ref in refs:
        kind = "artifact" if ref["kind"] == "chart" else "interpretive_claim"
        native = "p8-ref-" + fingerprint(ref)
        ident = "agent_p8_ref_" + fingerprint([owner, operation, native])[:32]
        row = service.repo.get(owner, kind, ident)
        if (
            row["status"] != "active"
            or row["subject_id"] != stored["subject_id"]
            or row.get("run_id") != step["run_id"]
            or type(row.get("epoch")) is not int
            or row["epoch"] != step["epoch"]
            or service.repo.is_revoked(owner, kind, ident)
        ):
            return None
        binding = {"id": stored["id"], "revision": stored["revision"], "document_id": doc["document_id"]}
        if (
            fingerprint(row.get("p8_reference")) != fingerprint(ref)
            or fingerprint(row.get("p8_document_record")) != fingerprint(binding)
            or fingerprint(row.get("source_versions")) != fingerprint(cache["snapshot"]["versions"])
        ):
            return None
        group = "artifacts" if kind == "artifact" else "claims"
        expected[group].append({"id": ident, "native_id": native, "revision": row["revision"]})
        versions[entity_dependency(kind, ident)] = row["revision"]
        if (
            kind == "interpretive_claim"
            and ident in publication["used_claim_ids"]
            and ref["pointer"].startswith("/boundary_alerts/")
        ):
            alert = doc["payload"]["boundary_alerts"][int(ref["pointer"].rsplit("/", 1)[-1])]
            kinds.add(alert["boundary_kind"])
    if any(fingerprint(data["persisted"][group]) != fingerprint(records) for group, records in expected.items()):
        return None
    return versions, kinds


def _published(service, ctx, step, current_snapshot, source):
    owner = ctx.owner
    publication = step["publication"]
    message = service.memory.get_source(owner, step["publication_message_id"], for_context=True)
    if (
        not validated_result(publication)
        or publication.get("message_id") != message["id"]
        or publication.get("meta", {}).get("core_run", {}).get("run_id") != step["run_id"]
        or publication.get("meta", {}).get("subject_id") != ctx.subject
        or publication.get("used_claim_ids") != message.get("used_claim_ids")
        or message["status"] != "active"
        or message.get("role") != "assistant"
        or message.get("run_id") != step["run_id"]
        or message.get("content") != publication["text"]
        or message.get("thread_id") != ctx.thread_id
        or message.get("conversation_id") != source.get("conversation_id")
        or set(message.get("case_ids", [])) - set(ctx.case_ids)
        or service.repo.is_revoked(owner, "message", message["id"])
        or (message["at_ms"], message["created_at"], message["id"])
        >= (source["at_ms"], source["created_at"], source["id"])
    ):
        return None
    checked = _document(service, owner, ctx.subject, step, profile_only=True)
    if checked is None:
        return None
    stored, cache, doc = checked
    if _profile(cache["snapshot"]) != _profile(current_snapshot):
        return None
    refs = _references(service, owner, step, cache, doc, stored, publication)
    if refs is None:
        return None
    versions, kinds = refs
    versions.update(
        {
            key: value
            for key, value in profile_versions(cache["snapshot"]).items()
            if key.startswith(("fact:", "message:"))
        }
    )
    versions.update(
        {
            "message:" + message["id"]: message["revision"],
            entity_dependency("artifact", stored["id"]): stored["revision"],
            entity_dependency("runtime_step", cache["id"]): cache["revision"],
        }
    )
    return message, versions, kinds


def prior_boundary_proofs(service, run, ctx, result, guidance):
    if ctx.private or ctx.crisis or not guidance:
        return {}
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        cache, _ = chart_cache(service, run, result)
        source = service.source(ctx, run["request"]["source_message_id"])
        rows = connection.execute(
            sql.SQL(
                "SELECT s.*,r.result AS publication,e.id AS publication_message_id FROM {} s "
                "JOIN {} r ON r.owner=s.owner AND r.id=s.run_id "
                "JOIN {} e ON e.owner=r.owner AND e.data->>'run_id'=r.id AND e.kind='message' "
                "WHERE r.owner=%s AND r.subject=%s AND r.runtime='v4' AND r.status='succeeded' "
                "AND r.cancel_requested_at IS NULL AND r.thread_id=%s AND r.id<>%s AND s.epoch=r.retry_epoch "
                "AND s.kind='tool' AND s.name='chart_compute' AND s.status='completed' "
                "AND s.finished_at IS NOT NULL AND s.error_code IS NULL AND s.output->>'ok'='true' "
                "AND e.status='active' AND e.data->>'role'='assistant' AND e.data->>'conversation_id'=%s "
                "ORDER BY e.created_at DESC,s.seq DESC LIMIT 20"
            ).format(
                service.repo.table("core_run_steps"),
                service.repo.table("core_runs"),
                service.repo.table("core_entities"),
            ),
            (ctx.owner, ctx.subject, ctx.thread_id, ctx.run_id, source.get("conversation_id")),
        ).fetchall()
        found = {}
        for step in rows:
            try:
                published = _published(service, ctx, step, cache["snapshot"], source)
                if published is None:
                    continue
                message, versions, kinds = published
                for item in guidance:
                    if (
                        item["rule_alias"] not in found
                        and item["boundary_kind"] in kinds
                        and canonical(item["text"]) in canonical(message["content"])
                    ):
                        found[item["rule_alias"]] = (message["id"], message["revision"], versions)
            except (CoreError, KeyError, TypeError, ValueError):
                continue
        return found
