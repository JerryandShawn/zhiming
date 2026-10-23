"""P3 execution overlays preserve the frozen measurement assertions and seeds."""

from pathlib import Path

import httpx
import pytest

from mingjing_core.models.quota_types import GuardRejected
from tools.eval import live, runner
from tools.eval.contracts import scenario_contract_hash
from tools.eval.runner import main, parser
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import (
    R3_IDS,
    REQUIRED_IDS,
    split_recovery_contract,
    write_corpus,
)

ROOT = Path(__file__).resolve().parents[3]


def test_46_unchanged_overlays_preserve_original_scoring_contracts_and_r3_is_explicit() -> None:
    frozen = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios")}
    overlays = load_scenarios(ROOT / "tools/eval/scenarios_v4")
    assert {case.id for case in overlays} == REQUIRED_IDS and len(REQUIRED_IDS) == 48
    for case in overlays:
        if case.id not in R3_IDS:
            assert scenario_contract_hash(case) == scenario_contract_hash(frozen[case.id])
        else:
            assert scenario_contract_hash(case) != scenario_contract_hash(frozen["X03"])
        assert all(
            set(action.model_dump(exclude_none=True)) <= {"text", "tool_call"}
            for step in case.scripted
            for action in step.model
        )


def test_r3_split_changes_only_authorized_channel_delivery_expectations(
    tmp_path: Path,
) -> None:
    source = ROOT / "tools/eval/scenarios"
    original = next(case for case in load_scenarios(source) if case.id == "X03")
    before = original.model_dump(mode="json")
    web, feishu = split_recovery_contract(original)
    assert original.model_dump(mode="json") == before
    for case, channel in ((web, "web"), (feishu, "feishu")):
        assert case.seed == original.seed and case.scripted == original.scripted
        assert [turn.user for turn in case.turns] == [turn.user for turn in original.turns]
        assert all(turn.channel == channel for turn in case.turns)
        assert all(turn.expect.db[0].model_dump() == original.turns[0].expect.db[0].model_dump() for turn in case.turns)
        assert case.turns[0].expect.events == ["run.step_committed", "run.crashed"]
        assert case.turns[0].expect.db[1].count == 0
        assert case.turns[1].expect.db[1].count == int(channel == "feishu")
        assert case.turns[1].action == original.turns[1].action
    (tmp_path / "X03.yaml").write_text("obsolete generated overlay", encoding="utf-8")
    write_corpus(source, tmp_path)
    assert {case.id for case in load_scenarios(tmp_path)} == REQUIRED_IDS
    assert not (tmp_path / "X03.yaml").exists()
    with pytest.raises(ValueError, match="Only the approved X03"):
        split_recovery_contract(web)


def test_v4_cli_requires_trusted_authorization_and_default_fake_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("Ungated live v4 must not access central PG, construct a target or send HTTP")

    assert parser().parse_args([]).target is None
    monkeypatch.setattr(runner, "_target", forbidden)
    monkeypatch.setattr(live.CentralLocation, "from_environment", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="Live preflight failed"):
        main(["--target", "v4", "--mode", "live"])
    monkeypatch.setenv("KIMI_API_KEY", "synthetic-cli-preflight-only")
    with pytest.raises(GuardRejected) as rejected:
        main(["--target", "v4", "--mode", "live"])
    assert rejected.value.kind == "manual_start_required"
    assert main(["--target", "v4", "--validate-only"]) == 0
