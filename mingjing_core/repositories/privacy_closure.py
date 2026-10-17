"""Compute the complete owner-local dependency closure before clearing bodies."""

from psycopg import sql


def linked_ids(entity):
    sources = set(entity.get("source_ids", [])) | {ref.get("message_id") for ref in entity.get("source_refs", [])}
    sources.update(value for key in ("message_id", "source_id") if (value := entity.get(key)))
    used = set(entity.get("fact_ids", [])) | set(entity.get("used_fact_ids", []))
    sources.update(entity.get("used_claim_ids", []))
    return sources, used


def closure_rows(repo, owner, kinds):
    with repo.transaction(owner) as connection:
        entities = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND kind=ANY(%s) AND status!='deleted'").format(
                repo.table("core_entities")
            ),
            (owner, list(kinds)),
        ).fetchall()
        runs = connection.execute(
            sql.SQL("SELECT id,state_version,request,status FROM {} WHERE owner=%s").format(repo.table("core_runs")),
            (owner,),
        ).fetchall()
    return [dict(repo._decode(row), entity_kind=row["kind"]) for row in entities], runs


def partial_sources(repo, owner, facts, explicit):
    selected = set(explicit)
    for revoked in repo.revocations(owner):
        metadata = revoked["metadata"]
        if revoked["kind"] == "source_span" and facts.intersection(metadata.get("fact_ids", [])):
            selected.add(metadata["message_id"])
    return selected


def contaminated_runs(rows, facts, sources, keys, runs, recomputable):
    for row in rows:
        if recomputable and row["status"] in ("revoked", "cancelled"):
            continue
        dependencies = set(row["state_version"])
        tainted = keys.intersection(dependencies) or any("fact:" + ident in dependencies for ident in facts)
        tainted = tainted or any("message:" + ident in dependencies for ident in sources)
        tainted = (
            tainted or row["request"].get("source_message_id") in sources or row["request"].get("message_id") in sources
        )
        if tainted or row["request"].get("parent_run") in runs:
            runs.add(row["id"])


def propagate(
    repo,
    owner,
    entities,
    run_rows,
    facts,
    sources,
    runs,
    redact,
    derived_kinds,
    recomputable,
    seed_entities=(),
    include_legacy=False,
):
    keys = {kind + ":" + ident for kind, ident in seed_entities}
    handled = set()
    while True:
        before = len(sources), len(runs), len(keys)
        contaminated_runs(run_rows, facts, sources, keys, runs, recomputable)
        for entity in entities:
            key = entity["entity_kind"], entity["id"]
            linked, used = linked_ids(entity)
            if key in handled or not (
                sources.intersection(linked)
                or facts.intersection(used)
                or entity.get("run_id") in runs
                or (
                    include_legacy
                    and entity.get("legacy_derived")
                    and not entity.get("source_ids")
                    and not entity.get("source_refs")
                )
            ):
                continue
            if entity["entity_kind"] == "message" and entity.get("role") in ("assistant", "tool"):
                if entity.get("run_id"):
                    runs.add(entity["run_id"])
                if not entity.get("redacted"):
                    if entity.get("run_id"):
                        redact(repo, owner, entity)
                    else:
                        repo.delete(owner, "message", entity["id"], expected_revision=entity["revision"])
            elif entity["entity_kind"] in derived_kinds:
                repo.delete(owner, entity["entity_kind"], entity["id"], expected_revision=entity["revision"])
            elif entity["entity_kind"] != "interpretive_claim":
                continue
            handled.add(key)
            sources.add(entity["id"])
            keys.add(entity["entity_kind"] + ":" + entity["id"])
        if before == (len(sources), len(runs), len(keys)):
            return
