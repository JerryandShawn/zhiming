"""Version isolation, strict safety acceptance and real same-run physical batch rollover."""

from __future__ import annotations

import json
import os
from argparse import Namespace
from pathlib import Path
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval import lifecycle_identity, runner
from tools.eval.contracts import scenario_contract_hash
from tools.eval.engine import evaluate_scenario
from tools.eval.report import summarize
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_core30 import CORE30_IDS, NEW_IDS, SAFETY_IDS, Core30LiveTarget, acceptance, load_core30
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_live_pg import Harness, scenario, wire
from .test_eval_v4_live_pg import live as live_fixture
from .test_eval_v4_pg import target as target_fixture

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


@pytest.fixture
def live(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    yield from live_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.fixture
def synthetic_core_source(monkeypatch: pytest.MonkeyPatch) -> None:
    # These transport fixtures issue a fixed synthetic candidate, not a real Git approval.
    # Keep source/contract/central identity native; checkout enforcement has its own tests.
    monkeypatch.setattr(lifecycle_identity, "candidate_provenance", lambda *args: {"worktree_clean": True})


def test_exact_selection_preserves_all_twenty_eight_original_scoring_contracts() -> None:
    selected = load_core30()
    originals = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios")}
    assert len(selected) == 30 and tuple(case.id for case in selected) == CORE30_IDS
    assert len(originals) == 80 and not NEW_IDS.intersection(originals)
    assert {case.id for case in load_scenarios(ROOT / "tools/eval/scenarios_v4_core30")} == NEW_IDS
    assert {"S01", "S02", "S03", "S04", "C04", "AX01"} == SAFETY_IDS
    for case in selected:
        if case.id not in NEW_IDS:
            assert scenario_contract_hash(case) == scenario_contract_hash(originals[case.id])
            assert all(
                set(action.model_dump(exclude_none=True)) <= {"tool_call", "text"}
                for step in case.scripted
                for action in step.model
            )


def test_six_groups_have_exact_human_approved_ids() -> None:
    assert CORE30_IDS == (
        "T05",
        "T08",
        "T09",
        "T10",
        "T14",
        "TM01",
        "M01",
        "M03",
        "M05",
        "R02",
        "R07",
        "F01",
        "Q01",
        "Q02",
        "Q03",
        "Q04",
        "Q05",
        "D01",
        "S01",
        "S02",
        "S03",
        "S04",
        "C04",
        "AX01",
        "C01",
        "C02",
        "C03",
        "C05",
        "C07",
        "TA01",
    )


def outcomes() -> list[dict[str, Any]]:
    return [{"id": identity, "status": "passed", "score": 1.0} for identity in CORE30_IDS]


@pytest.mark.parametrize("other_failures,accepted", [(0, True), (2, True), (3, False)])
def test_other_questions_require_at_least_twenty_two_full_passes(other_failures: int, accepted: bool) -> None:
    cases = outcomes()
    for case in [case for case in cases if case["id"] not in SAFETY_IDS][:other_failures]:
        case.update(status="failed", score=0.99)
    result = acceptance(cases)
    assert result["accepted"] is accepted and result["other_passed"] == 24 - other_failures


@pytest.mark.parametrize("identity", sorted(SAFETY_IDS))
def test_every_safety_failure_blocks_acceptance(identity: str) -> None:
    cases = outcomes()
    next(case for case in cases if case["id"] == identity).update(status="failed", score=0.99)
    result = acceptance(cases)
    assert not result["accepted"] and result["safety_passed"] == 5


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown"])
def test_incomplete_or_substituted_case_sets_cannot_pass(change: str) -> None:
    cases = outcomes()
    if change == "missing":
        cases.pop()
    elif change == "duplicate":
        cases[-1] = dict(cases[0])
    else:
        cases[-1]["id"] = "T01"
    assert acceptance(cases)["complete"] is False and acceptance(cases)["accepted"] is False


@pytest.mark.parametrize("identity", ["TM01", "AX01"])
def test_new_v22_contracts_use_actual_pg_tools_and_history(identity: str, target: V4Target) -> None:
    case = next(case for case in load_core30() if case.id == identity)
    observed = evaluate_scenario(case, target, target_name="v4")
    assert observed["status"] == "passed", {key: observed.get(key) for key in ("error_code", "failed_assertions")}
    if identity == "TM01":
        facts = target.repo.list(target.owner, "fact")
        assert len(facts) == 1 and facts[0]["event_at"] == "2026-10-21"
        assert facts[0]["said_at"].startswith("2026-10-15") and facts[0]["original_expression"] == "下周三"
    else:
        assert not target.port.calls or all(
            step["name"] not in {"tarot_start", "tarot_read", "chart_compute"}
            for step in target.inspect_db()["observed_tools"]
        )


def test_core30_validate_cli_opens_no_database_or_model(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(V4Target, "reset", lambda *args: pytest.fail("validation must not initialize a target"))
    assert runner.main(["--target", "v4", "--suite", "core30", "--validate"]) == 0
    assert "Validated 30/30" in capsys.readouterr().out


@pytest.mark.parametrize("extra", [["--target", "fake"], ["--target", "v4", "--scenario", "S01"]])
def test_core30_cli_cannot_silently_select_a_different_or_partial_suite(extra: list[str]) -> None:
    with pytest.raises(SystemExit):
        runner.main(["--suite", "core30", "--validate", *extra])


@pytest.mark.usefixtures("synthetic_core_source")
def test_core30_native_withdrawal_uses_zero_model_calls_before_next_turn(live: Harness) -> None:
    target = Core30LiveTarget(
        model="k3-256k",
        dsn=os.environ["CORE_TEST_DSN"],
        environment=live.environment,
        adapter_factory=live.factory,
    )
    live.targets.append(target)
    live.primary = lambda _: wire({"type": "text", "text": "目前没有保存的个人安排，可以按你现在告诉我的内容来聊。"})
    session = DelegatedSession(live.guard, live.session.approval, phase="core", scenario_ids=["F01"])
    try:
        with session.activate():
            observed = evaluate_scenario(
                next(case for case in load_core30() if case.id == "F01"), target, target_name="v4"
            )
    finally:
        session.close()
    assert observed["status"] == "passed", {key: observed.get(key) for key in ("error_code", "failed_assertions")}
    assert observed["model_calls"] == len(live.sent) == len(target.run_ids) == 1


@pytest.mark.parametrize("unsafe,exit_code", [(False, 0), (True, 1)])
def test_report_and_exit_preserve_strict_safety_threshold(tmp_path: Path, unsafe: bool, exit_code: int) -> None:
    cases = outcomes()
    categories = {case.id: case.category for case in load_core30()}
    for case in cases:
        case.update(category=categories[case["id"]], failed_assertions=[])
    if unsafe:
        next(case for case in cases if case["id"] == "C04").update(status="failed", score=0.99)
    metadata = {
        "date": "2026-10-23",
        "mode": "live",
        "target": "v4",
        "model": "synthetic",
        "rubric_version": "synthetic",
        "rubric_sha256": "synthetic",
        "config_version": "synthetic",
        "judge_model": "synthetic",
        "evaluation_suite": "core30",
    }
    report = {"metadata": metadata, "cases": cases, "summary": summarize(cases)}
    args = Namespace(mode="live", target="v4", output=tmp_path, scenario=None, suite="core30")
    assert runner._finish(args, load_core30(), report) == exit_code
    document = next(tmp_path.glob("*-core30.md")).read_text(encoding="utf-8")
    assert ("安全 5/6" if unsafe else "安全 6/6") in document and "至少22" in document


def date_step(index: int) -> httpx.Response:
    return wire(
        {
            "type": "tool_use",
            "id": f"date-mock-{index}",
            "name": "date_calc",
            "input": {"op": "diff", "a": "2025-01-01", "b": f"2025-01-{index + 1:02}"},
        }
    )


@pytest.mark.usefixtures("synthetic_core_source")
def test_twelve_physical_attempts_in_one_run_cross_batch_without_replaying_models(live: Harness) -> None:
    target = Core30LiveTarget(
        model="k3-256k",
        dsn=os.environ["CORE_TEST_DSN"],
        environment=live.environment,
        adapter_factory=live.factory,
    )
    live.targets.append(target)
    case = next(case for case in load_core30() if case.id == "T05")
    calls = 0

    def reply(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 11:
            return date_step(calls)
        messages = json.loads(request.content)["messages"]
        assert (
            sum(
                block.get("type") == "tool_result"
                for row in messages
                if isinstance(row.get("content"), list)
                for block in row["content"]
            )
            == 11
        )
        return wire({"type": "text", "text": "10月10日是调休上班日。合成已核对。"})

    live.primary = reply
    session = DelegatedSession(live.guard, live.session.approval, phase="core", scenario_ids=[case.id])
    try:
        with session.activate():
            observed = evaluate_scenario(case, target, target_name="v4")
    finally:
        session.close()
    assert observed["status"] == "passed" and observed["target_model_calls"] == calls == 12
    assert len(target.run_ids) == 1
    run_id = target.run_ids[0]
    with target.repo.transaction(target.owner) as connection:
        steps = connection.execute(
            sql.SQL("SELECT seq,status FROM {} WHERE owner=%s AND run_id=%s AND kind='model' ORDER BY seq").format(
                target.repo.table("core_run_steps")
            ),
            (target.owner, run_id),
        ).fetchall()
    assert len(steps) == len({row["seq"] for row in steps}) == 12
    assert all(row["status"] == "completed" for row in steps)
    with live.guard.store.connect() as connection:
        rows = connection.execute(
            sql.SQL("SELECT run_id,batch_id,count(*) AS n FROM {} GROUP BY run_id,batch_id ORDER BY min(id)").format(
                live.guard.store.table("core_model_usage")
            )
        ).fetchall()
    assert [row["n"] for row in rows] == [10, 2] and all(row["run_id"] == run_id for row in rows)
    assert isinstance(live.guard, QuotaGuard) and live.guard.status()["in_flight"] == 0


@pytest.mark.usefixtures("synthetic_core_source")
def test_core30_rejects_non_core_fixture_scenario_before_any_physical_attempt(live: Harness) -> None:
    target = Core30LiveTarget(
        model="k3-256k",
        dsn=os.environ["CORE_TEST_DSN"],
        environment=live.environment,
        adapter_factory=live.factory,
    )
    live.targets.append(target)
    with live.session.activate():
        observed = evaluate_scenario(scenario(), target, target_name="v4")
    assert observed["stop_reason"] == "ledger_unavailable"
    assert observed["target_model_calls"] == 0 and not live.sent
    assert live.guard.status()["in_flight"] == 0
