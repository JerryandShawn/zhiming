"""Verify critic and one revision against real completed model rows before commit."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.agent.loop_codec import assistant_from
from mingjing_core.agent.prompts import load_prompts
from mingjing_core.agent.review import CriticVerdict, TrustedReviewReceipt, text_sha
from mingjing_core.application.agent_options import load_options, options_binding
from mingjing_core.application.agent_options_review import critic_input
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def model_step(repo: PostgresRepository, run: dict[str, Any], seq: int, name: str) -> str:
    with repo.transaction(run["owner"]) as connection:
        row = connection.execute(
            sql.SQL(
                "SELECT kind,name,status,output,error_code FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], seq),
        ).fetchone()
    if not row or (row["kind"], row["name"], row["status"], row["error_code"]) != ("model", name, "completed", None):
        raise EvidenceError("评审证明缺少已完成的真实模型步骤")
    return assistant_from(row["output"]).text


class ReviewProofStore:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo = repo

    def save(
        self,
        run: dict[str, Any],
        *,
        draft: JournalStep,
        critic: JournalStep,
        revision: JournalStep | None,
        final: str,
        versions: dict[str, int],
        prompt_sha256: str,
    ) -> TrustedReviewReceipt:
        with self.repo.transaction(run["owner"]) as connection:
            current = Journal(self.repo, run["owner"])._leased(connection, run)
            draft_text = model_step(self.repo, current, draft.seq, "")
            selected = load_options(self.repo, current)
            actual_input = critic_input(self.repo, current, critic.seq, draft_text, selected)
            verdict = CriticVerdict.parse(model_step(self.repo, current, critic.seq, "critic"), actual_input)
            revision_id = f"revision-{current['id']}-e{current['retry_epoch']}" if revision else None
            if revision:
                if verdict.verdict != "revise" or model_step(self.repo, current, revision.seq, "revision") != final:
                    raise EvidenceError("评审改写与真实修订步骤不符")
            elif verdict.verdict != "pass" or draft_text != final:
                raise EvidenceError("评审通过的正文与初稿不符")
            value = {
                "schema": "agent-review-proof-v1",
                "draft_seq": draft.seq,
                "critic_seq": critic.seq,
                "revision_seq": revision.seq if revision else None,
                "draft_sha256": text_sha(draft_text),
                "final_sha256": text_sha(final),
                "reviewed_sha256": text_sha(actual_input),
                **options_binding(selected),
                "options_suppressed": bool(revision and selected),
                "prompt_sha256": prompt_sha256,
                "public": verdict.public(revised=revision is not None, revision_id=revision_id),
            }
            return self._persist(current, value, versions)

    def _persist(self, run: dict[str, Any], value: dict[str, Any], versions: dict[str, int]) -> TrustedReviewReceipt:
        ident = f"{run['id']}:e{run['retry_epoch']}:agent_review"
        self.repo.put(
            run["owner"],
            "runtime_step",
            ident,
            {
                "schema": "agent-review-proof-v1",
                "stage": "agent_review",
                "run_id": run["id"],
                "epoch": run["retry_epoch"],
                "output": value,
                "output_sha256": fingerprint(value),
                "source_ids": [key[8:] for key in versions if key.startswith("message:")],
                "fact_ids": [key[5:] for key in versions if key.startswith("fact:")],
            },
            subject=run["subject"],
            expected_revision=0,
            operation_id="agent-review:" + ident,
        )
        return TrustedReviewReceipt(
            run["owner"], run["id"], run["retry_epoch"], ident, fingerprint(value), value["public"]
        )

    def verify(self, receipt: TrustedReviewReceipt, run: dict[str, Any], text: str) -> None:
        if (receipt.owner, receipt.run_id, receipt.epoch) != (run["owner"], run["id"], run["retry_epoch"]):
            raise EvidenceError("评审证明不属于当前运行")
        row = self.repo.get(run["owner"], "runtime_step", receipt.proof_id)
        value = row.get("output")
        if (
            row["subject_id"] != run["subject"]
            or row.get("run_id") != run["id"]
            or row.get("epoch") != run["retry_epoch"]
            or row.get("schema") != "agent-review-proof-v1"
            or fingerprint(value) != receipt.proof_sha256
            or fingerprint(value) != row.get("output_sha256")
        ):
            raise EvidenceError("评审证明已失效")
        draft = model_step(self.repo, run, value["draft_seq"], "")
        selected = load_options(self.repo, run)
        actual_input = critic_input(self.repo, run, value["critic_seq"], draft, selected)
        verdict = CriticVerdict.parse(model_step(self.repo, run, value["critic_seq"], "critic"), actual_input)
        revised = value["revision_seq"] is not None
        actual = model_step(self.repo, run, value["revision_seq"], "revision") if revised else draft
        revision_id = f"revision-{run['id']}-e{run['retry_epoch']}" if revised else None
        expected_public = verdict.public(revised=revised, revision_id=revision_id)
        if (
            actual != text
            or value["draft_sha256"] != text_sha(draft)
            or value["final_sha256"] != text_sha(text)
            or (verdict.verdict == "revise") != revised
            or receipt.public() != value["public"]
            or value["public"] != expected_public
            or value["prompt_sha256"] != load_prompts().manifest["files"]["critic"]["sha256"]
            or any(value.get(key) != item for key, item in options_binding(selected).items())
            or value.get("reviewed_sha256", value["draft_sha256"]) != text_sha(actual_input)
            or value.get("options_suppressed", False) != bool(revised and selected)
        ):
            raise EvidenceError("评审通过 / 改写正文与持久证据不符")
        self._revision_count(run)

    def _revision_count(self, run: dict[str, Any]) -> None:
        with self.repo.transaction(run["owner"]) as connection:
            count = connection.execute(
                sql.SQL(
                    "SELECT count(*) AS count FROM {} WHERE owner=%s AND run_id=%s "
                    "AND epoch=%s AND kind='model' AND name='revision' AND status='completed'"
                ).format(self.repo.table("core_run_steps")),
                (run["owner"], run["id"], run["retry_epoch"]),
            ).fetchone()["count"]
        if count > 1:
            raise EvidenceError("本周期不能生成多次评审修订")
