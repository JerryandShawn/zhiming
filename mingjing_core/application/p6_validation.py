"""Default-off draft: real P6 structural checks plus advisory legacy lint, without critic calls."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

from psycopg import sql

from mingjing_core.agent.loop_cycle import LoopCycle, LoopOutcome
from mingjing_core.agent.options import options_text
from mingjing_core.agent.review import text_sha
from mingjing_core.application.agent_options import load_options
from mingjing_core.application.agent_runtime_state import RuntimeState
from mingjing_core.application.p6_projection import lint_context, receipt_projection, trusted_records
from mingjing_core.application.p6_records import P6Records
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.validation.p6_candidate.legacy_lint import LintContext, lint
from mingjing_core.validation.p6_candidate.structural import structural_check
from mingjing_core.validation.p6_candidate.structural_contracts import StructuralContext


class P6ValidationBridge:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo, self.records = repo, P6Records(repo)

    def apply(self, cycle: LoopCycle, outcome: LoopOutcome, *, phase: str) -> LoopOutcome:
        run = RuntimeState(self.repo).authority(cycle.run["owner"], cycle.run["id"], cycle.run["lease_token"])
        if run["retry_epoch"] != cycle.run["retry_epoch"] or run["state_version"] != outcome.versions:
            raise EvidenceError("P6检查不属于当前运行版本")
        records = trusted_records(self.repo, run, outcome)
        receipts = receipt_projection(self.repo, run, records)
        clock = self.records.clock(run)
        settings = self.repo.assert_scope(run["owner"], run["subject"])["settings"]
        context = StructuralContext(
            clock=clock,
            timezone=settings.get("timezone", "Asia/Shanghai"),
            aliases=frozenset(records),
            receipts=receipts,
            ask_user_calls=self._asks(run),
            last_model_text=outcome.text,
            farewell=False,
            critic_available=False,
        )
        prepared_lint = lint_context(self.repo, run, outcome, records)
        selected = load_options(self.repo, run)
        checked, codes, warnings = run_checks(
            outcome.text, context, prepared_lint, selected.value if selected else None
        )
        value = {
            "mode": "evidence_only" if checked != outcome.text else "record_only",
            "program_at": clock.now().isoformat(),
            "timezone": context.timezone,
            "before_sha256": text_sha(outcome.text),
            "after_sha256": text_sha(checked),
            "structural": dict(Counter(codes)),
            "lint": dict(Counter(warnings)),
        }
        self.records.record(run, phase, value)
        return replace(outcome, text=checked)

    def _asks(self, run: dict[str, Any]) -> int:
        with self.repo.transaction(run["owner"]) as connection:
            return connection.execute(
                sql.SQL(
                    "SELECT count(*) AS n FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                    "AND kind='tool' AND name='ask_user' AND status='completed' AND output->>'ok'='true'"
                ).format(self.repo.table("core_run_steps")),
                (run["owner"], run["id"], run["retry_epoch"]),
            ).fetchone()["n"]


def run_checks(
    text: str, context: StructuralContext, prepared_lint: LintContext, options: dict[str, Any] | None
) -> tuple[str, list[str], list[str]]:
    # Only pure validation is fail-open. PG projections, authority and durable
    # records run outside this function and retain the strict publication fence.
    checked, codes = text, []
    try:
        result = structural_check(text, context)
        checked, codes = result.text, [item.code for item in result.findings]
    except Exception:
        codes = ["p6_validation_internal_error"]
    try:
        complete = checked + ("\n" + options_text(options) if options else "")
        final = dict(prepared_lint.final_answer, plain_summary=checked[:6000] or "本轮回答待整理")
        warnings = [item.rule for item in lint(complete, replace(prepared_lint, final_answer=final))]
    except Exception:
        warnings = ["p6_lint_internal_error"]
    return checked, codes, warnings
