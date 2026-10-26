"""Project only native synthetic evaluation rows into private judge evidence."""

from copy import deepcopy

from .v4_context_observations import context_observations
from .v4_tool_effects import tool_effects


def judge_evidence(target, run):
    context = context_observations(target.repo, target.owner, run)
    effects = tool_effects(target.repo, target.owner, run["id"])
    claims = []
    for claim in effects["chart_claims"]:
        claims.append(
            {"alias": claim.get("alias", claim.get("claim_id")), "text": claim.get("text", claim.get("statement", ""))}
        )
    return {
        "now": context.get("now", ""),
        "injected_facts": context.get("injected_facts", []),
        "seed_bindings": deepcopy(target.seeder.ids),
        "memories": [
            {key: deepcopy(row.get(key)) for key in ("id", "kind", "content", "summary", "status")}
            for row in target.repo.list(target.owner, "fact", include_deleted=True)
        ],
        "chart_claims": claims,
    }
