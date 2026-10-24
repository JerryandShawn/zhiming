"""Run the R11 first-release scripts on one clean candidate; never call live models."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
from psycopg import sql

from mingjing_core.models.quota_gate import CORE_IDS, DATES_IDS, P3_IDS
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval import runner
from tools.eval.contracts import scenario_contract_hash
from tools.eval.live import candidate_provenance
from tools.eval.schema import load_scenario
from tools.eval.targets.v4_core30 import CORE30_IDS
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_full_corpus import write_full_corpus
from tools.eval.targets.v4_http_faults import HttpFaultPort
from tools.eval.targets.v4_target import V4Target

DEFERRED = {
    "L02": "首发仅Kimi；多模型对照延后",
    "M08": "第二批P5记忆2.0",
    **{f"P{i:02}": "后续P7主动跟进" for i in range(1, 7)},
    "X01": "第三批P6评审员",
    "X02": "首发无跨供应商降级；另验X02-r11等价断言",
    "X06": "第三批P6评审员",
    "X08": "第三批P4真流式",
}
REQUIRED = {"p3": P3_IDS, "date_checks": DATES_IDS, "core": CORE_IDS, "core30": frozenset(CORE30_IDS)}


def _require(value: object) -> None:
    if not value:
        raise ValueError("R11_SCRIPTED_GATE_REJECTED")


def _state(target: V4Target) -> list[str]:
    with target.repo.transaction(target.owner) as connection:
        return [
            connection.execute(
                sql.SQL(
                    "SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,'[]')) AS digest "
                    "FROM {} t"
                ).format(target.repo.table(name))
            ).fetchone()["digest"]
            for name in ("core_entities", "core_runs", "core_run_steps", "delivery_outbox")
        ]


def x02_equivalent() -> dict[str, Any]:
    """Actual retries exhaust on one provider; original X02 gold remains unchanged."""
    original = load_scenario(runner.EVAL_ROOT / "scenarios/X02.yaml")
    scenario = execution_overlay(original)
    target, previous = V4Target(), get_clock()
    try:
        set_clock(FrozenClock(datetime.fromisoformat(scenario.clock)))
        seed = scenario.seed.model_dump(mode="json")
        seed.update(
            controls={},
            _scenario_id="X02-r11",
            _clock=scenario.clock,
            _scripted=[step.model_dump(exclude_none=True) for step in scenario.scripted],
        )
        target.reset(seed)
        # Only the provider transport is synthetic; queues, runtime and commits are native.
        port = HttpFaultPort((503, 503, 503, 503))
        target.port = target.runtime.port = port
        turn = scenario.turns[0].model_dump(mode="json", exclude={"expect"}, exclude_none=True)
        result = target.send({**turn, "_index": 1})
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        proof, before = port.proof(), _state(target)
        _require(run["status"] == "succeeded" and result.text == run["result"]["text"])
        _require(result.text and any(word in result.text for word in ("稍后", "暂时", "再试")))
        _require([row["http_status"] for row in proof["attempts"]] == [503] * 4)
        _require(proof["mock_http_requests"] == proof["adapter_http_requests"] == 4)
        _require(len(set(proof["selected_models"])) == 1 and proof["success_actions_consumed"] == 0)
        # Read the already committed answer through the real public runtime boundary.
        replay = target.runtime.execute(target.service, target.owner, run["id"], run["lease_token"])
        _require(replay == run["result"] and port.calls == 4 and _state(target) == before)
        return {
            "id": "X02-r11",
            "status": "passed",
            "score": 1,
            "original_contract_sha256": scenario_contract_hash(original),
            "mock_http_requests": 4,
            "external_provider_requests": 0,
            "friendly_failure": True,
            "committed_answer_preserved": True,
            "repeat_writes": 0,
        }
    finally:
        target.close()
        set_clock(previous)


def assess(reports: dict[str, dict], candidate: str, source: str, x02: dict) -> dict[str, Any]:
    groups = {}
    for name, identities in REQUIRED.items():
        report = reports[name]
        meta, cases = report["metadata"], report["cases"]
        _require(meta.get("candidate_commit") == candidate and meta.get("source_sha256") == source)
        _require(meta.get("worktree_clean") is True and meta.get("status") == "complete")
        _require(meta.get("mode") == "scripted" and meta.get("target") == "v4")
        _require(meta.get("external_provider_requests") == 0 and not meta.get("stop_reason"))
        ids = [row["id"] for row in cases]
        _require(len(ids) == len(identities) and set(ids) == identities)
        needed = identities - set(DEFERRED) if name == "core" else identities
        passed = {row["id"] for row in cases if row["status"] == "passed" and row["score"] == 1}
        _require(needed <= passed)
        _require(all(row.get("v4_evidence", {}).get("external_provider_requests") == 0 for row in cases))
        groups[name] = {
            "mode": "scripted",
            "target": "v4",
            "status": "complete",
            "candidate_commit": candidate,
            "source_sha256": source,
            "worktree_clean": True,
            "count": len(needed),
            "passed": len(needed),
            "physical_requests": 0,
            "case_ids": sorted(needed),
        }
    _require(x02.get("id") == "X02-r11" and x02.get("status") == "passed" and x02.get("score") == 1)
    _require(x02.get("external_provider_requests") == x02.get("repeat_writes") == 0)
    _require(x02.get("friendly_failure") is True and x02.get("committed_answer_preserved") is True)
    return {
        "schema": "first-release-scripted-gate-r11",
        "synthetic": False,
        "candidate_commit": candidate,
        "source_sha256": source,
        "worktree_clean": True,
        **groups,
        "x02_equivalent": x02,
        "deferred": DEFERRED,
        "original_core_count": len(CORE_IDS),
        "equivalent": None,
    }


@contextmanager
def offline_only():
    def forbidden(*args, **kwargs):
        raise RuntimeError("R11_EXTERNAL_HTTP_FORBIDDEN")

    import urllib.request

    native = httpx.HTTPTransport.handle_request

    def loopback_only(transport, request):
        if request.url.scheme != "http" or request.url.host not in {"127.0.0.1", "::1"}:
            return forbidden()
        return native(transport, request)

    with (
        patch.object(httpx.HTTPTransport, "handle_request", loopback_only),
        patch.object(urllib.request, "urlopen", forbidden),
    ):
        yield


def run(candidate: str, output: Path) -> dict[str, Any]:
    candidate_provenance(runner.ROOT, candidate)
    private = runner.ROOT / "private/candidate-eval" / candidate
    _require(output.is_absolute() and output.is_relative_to(private) and not output.exists())
    output.mkdir(parents=True)
    full = output / "original-81-corpus"
    write_full_corpus(runner.EVAL_ROOT / "scenarios", full)
    selections = {
        "p3": runner.EVAL_ROOT / "scenarios_v4",
        "date_checks": runner.EVAL_ROOT / "scenarios_v4_dates",
        "core": full,
        "core30": None,
    }
    reports, paths = {}, {}
    source = runner._source_digest()
    with offline_only():
        for name, corpus in selections.items():
            destination = output / name
            args = ["--mode", "scripted", "--target", "v4", "--candidate", candidate, "--output", str(destination)]
            args += ["--suite", "core30"] if corpus is None else ["--scenarios", str(corpus)]
            result = runner.main(args)
            _require(result in ({0, 1} if name == "core" else {0}))
            files = list(destination.glob("*.json"))
            _require(len(files) == 1)
            reports[name] = json.loads(files[0].read_text(encoding="utf-8"))
            paths[name] = str(files[0].relative_to(runner.ROOT))
        x02 = x02_equivalent()
    candidate_provenance(runner.ROOT, candidate)
    _require(source == runner._source_digest())
    assessment = assess(reports, candidate, source, x02)
    assessment["reports"] = paths
    # This derived assessment is not a new model approval or a real probe result.
    with (output / "assessment.json").open("x", encoding="utf-8") as stream:
        json.dump(assessment, stream, ensure_ascii=False, indent=2)
    return assessment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.candidate, args.output)
    except Exception:
        print("R11_BLOCKED_REPORTS_RETAINED")
        return 2
    print(
        json.dumps(
            {
                "candidate": args.candidate,
                "p3": result["p3"]["passed"],
                "dates": result["date_checks"]["passed"],
                "core": result["core"]["passed"],
                "core30": result["core30"]["passed"],
                "x02_equivalent": "passed",
                "real_requests": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
