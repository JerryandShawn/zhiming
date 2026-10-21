"""Only a real completed successful card from this run and epoch can be public."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.agent.options import project_options
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


@dataclass(frozen=True)
class StoredOptions:
    seq: int
    source_sha256: str
    value: dict[str, Any] = field(repr=False)

    def binding(self) -> dict[str, Any]:
        return {
            "options_seq": self.seq,
            "options_source_sha256": self.source_sha256,
            "options_sha256": fingerprint(self.value),
        }


def load_options(repo: PostgresRepository, run: dict[str, Any]) -> StoredOptions | None:
    with repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT seq,output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' "
                "AND name='present_options' AND status='completed' AND error_code IS NULL ORDER BY seq DESC"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"]),
        ).fetchall()
    for row in rows:
        try:
            result = ToolResult.model_validate(row["output"])
        except (ValidationError, TypeError, ValueError):
            raise EvidenceError("真实决策步骤输出已损坏") from None
        if result.ok:
            if result.ends_turn or result.receipt is not None or set(result.data) != {"options"}:
                raise EvidenceError("真实决策步骤包含未授权的效果")
            return StoredOptions(
                row["seq"], fingerprint(row["output"]), project_options(run, row["seq"], result.data["options"])
            )
    return None


def options_binding(options: StoredOptions | None) -> dict[str, Any]:
    return options.binding() if options else dict(options_seq=None, options_source_sha256=None, options_sha256=None)
