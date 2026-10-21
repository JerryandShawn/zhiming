"""Bind critic card judgments to the actual private request and completed response."""

from __future__ import annotations

import json
from typing import Any

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.agent.journal import input_fingerprint
from mingjing_core.agent.loop_codec import assistant_from
from mingjing_core.agent.options import review_material
from mingjing_core.agent.review import CriticVerdict
from mingjing_core.application.agent_options import StoredOptions
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def critic_input(
    repo: PostgresRepository, run: dict[str, Any], seq: int, draft: str, options: StoredOptions | None
) -> str:
    ident = f"{run['id']}:e{run['retry_epoch']}:agent_model_request:{seq}"
    snapshot = repo.get(run["owner"], "runtime_step", ident)
    output = snapshot.get("output")
    if (
        snapshot["subject_id"] != run["subject"]
        or (snapshot.get("run_id"), snapshot.get("epoch"), snapshot.get("seq")) != (run["id"], run["retry_epoch"], seq)
        or snapshot.get("schema") != "agent-model-request-v1"
        or snapshot.get("stage") != "agent_model_request"
        or snapshot["status"] != "active"
        or fingerprint(output) != snapshot.get("output_sha256")
        or snapshot.get("input_fp") != critic_fingerprint(repo, run, seq)
    ):
        raise EvidenceError("评审原始请求证明已失效")
    try:
        identity = {
            "messages": output["budget"]["messages"],
            "tools": output["budget"]["tools"],
            "tool_choice": output["choice"],
            "source_versions": output["versions"],
        }
        users = [row["content"] for row in identity["messages"] if row["role"] == "user"]
        material = json.loads(users[-1]) if len(users) == 1 else None
        valid = (
            output["role"] == output["name"] == "critic"
            and identity["tools"] == []
            and identity["tool_choice"] == "auto"
            and snapshot["input_fp"] == input_fingerprint("model", "critic", identity)
            and isinstance(material, dict)
            and material.get("draft") == draft
            and material.get("options") == (options.value if options else None)
        )
    except (KeyError, TypeError, ValueError, IndexError):
        valid = False
    if not valid:
        raise EvidenceError("评审实际请求没有包含真实初稿与决策卡")
    return review_material(draft, options.value if options else None)


def critic_fingerprint(repo: PostgresRepository, run: dict[str, Any], seq: int) -> str:
    with repo.transaction(run["owner"]) as connection:
        row = connection.execute(
            sql.SQL(
                "SELECT kind,name,status,error_code,input_fp FROM {} "
                "WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], seq),
        ).fetchone()
    if row is None or (row["kind"], row["name"], row["status"], row["error_code"]) != (
        "model",
        "critic",
        "completed",
        None,
    ):
        raise EvidenceError("评审请求缺少真实已完成的对应步骤")
    return row["input_fp"]


def card_veto(repo: PostgresRepository, run: dict[str, Any], options: StoredOptions | None) -> bool:
    if options is None:
        return False
    with repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT seq,output,input_fp FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='model' AND name='critic' AND status='completed' AND error_code IS NULL AND seq>%s"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], options.seq),
        ).fetchall()
    for row in rows:
        ident = f"{run['id']}:e{run['retry_epoch']}:agent_model_request:{row['seq']}"
        snapshot = repo.get(run["owner"], "runtime_step", ident)
        try:
            messages = snapshot["output"]["budget"]["messages"]
            material = json.loads(next(item["content"] for item in messages if item["role"] == "user"))
            draft = material["draft"]
        except (KeyError, TypeError, ValueError, StopIteration):
            raise EvidenceError("评审原始卡片资料无法核验") from None
        actual = critic_input(repo, run, row["seq"], draft, options)
        if snapshot.get("input_fp") != row["input_fp"]:
            raise EvidenceError("评审模型步骤与原始请求指纹不符")
        try:
            verdict = CriticVerdict.parse(assistant_from(row["output"]).text, actual)
        except (ValidationError, ValueError, EvidenceError):
            continue
        if verdict.verdict == "revise":
            return True
    return False
