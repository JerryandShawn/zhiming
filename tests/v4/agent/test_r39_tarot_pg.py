import pytest
from datetime import datetime
from mingjing_core.timekit.clock import FrozenClock, set_clock, get_clock
from tools.eval.targets.v4_target import V4Target
from tools.eval.targets.v4_live import V4LiveTarget
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.schema import load_scenario


@pytest.mark.parametrize("draw_source", ["pick", "auto"])
@pytest.mark.parametrize("omit_identifier", [False, True])
def test_native_live_tarot_action_path(draw_source, omit_identifier):
    case = execution_overlay(load_scenario("tools/eval/scenarios/TA01.yaml"))
    if omit_identifier:
        case.scripted[1].model[0].tool_call.arguments.clear()
    case.scripted[0].model[0].tool_call.arguments["draw_source"] = draw_source
    target = V4Target()
    old = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat(case.clock)))
    try:
        seed = case.seed.model_dump(mode="json", exclude_none=True)
        seed.update(
            _scenario_id=case.id, _scripted=[s.model_dump(mode="json", exclude_none=True) for s in case.scripted]
        )
        target.reset(seed)
        target._draw_selection = lambda turn: V4LiveTarget._draw_selection(target, turn)
        for i, turn in enumerate(case.turns, 1):
            result = target.send({**turn.model_dump(mode="json", exclude={"expect"}, exclude_none=True), "_index": i})
            assert not result.error, result.error
            disclosures = result.metadata["tool_disclosures"]
            assert disclosures and all(row["trimmed_known"] for row in disclosures)
            assert all(len(row["visible"]) <= 15 and isinstance(row["trimmed"], list) for row in disclosures)
            assert target.case_evidence()["tool_visibility_by_turn"][-1]["tool_disclosures"] == disclosures
            result.db = target.inspect_db()
            from tools.eval.judges import check_assertions

            assert all(c.passed for c in check_assertions(turn.expect.model_dump(exclude_none=True), result))
            if i == 2:
                assert result.metadata["prior_turns"][0]["receipts"]
                assert any("tarot_read" in names for names in result.metadata["visible_tools_per_request"])
                assert "tarot_read" in result.metadata["actual_tool_names"]
                systems = [
                    m.content
                    for request in target.port.requests
                    for m in request["messages"]
                    if m.role == "system" and "本轮用户已揭示牌阵" in m.content
                ]
                assert systems and '"id"' in systems[-1] and '"cards"' not in systems[-1]
    finally:
        target.close()
        set_clock(old)
