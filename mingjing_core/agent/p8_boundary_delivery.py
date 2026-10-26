"""Choose the brief native wording only after verifying an earlier public reply."""

import json
from dataclasses import replace

from mingjing_core.application.p8_boundary_history import prior_boundary_proofs
from mingjing_core.domain.contracts import RevisionConflict


def boundary_delivery(cycle, prepared, result, message):
    output = json.loads(message.content)
    guidance = output["data"].get("boundary_guidance", [])
    if not guidance:
        return message
    repo = cycle.registry.service.repo
    with repo.transaction(cycle.run["owner"]) as connection:
        proofs = prior_boundary_proofs(cycle.registry.service, cycle.run, prepared.context, result, guidance)
        current = cycle.journal._leased(connection, cycle.run)
        versions = dict(current["state_version"])
        for item in guidance:
            item["display_mode"], item["already_explained"] = "full", False
            if item["rule_alias"] not in proofs:
                continue
            ident, revision, dependencies = proofs[item["rule_alias"]]
            for key, value in dependencies.items():
                if key in versions and versions[key] != value:
                    raise RevisionConflict("临界说明的既有发布依赖已改变")
                versions[key] = value
            item.update(
                text=item["brief_text"],
                display_mode="brief",
                already_explained=True,
                previous_publication={"message_id": ident, "revision": revision},
            )
        if proofs:
            if not repo.verify_versions(cycle.run["owner"], versions):
                raise RevisionConflict("临界说明来源已改变")
            repo.set_run_dependencies(cycle.run["owner"], cycle.run["id"], versions, cycle.run["lease_token"])
            cycle.versions = versions
    return replace(
        message, content=json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    )
