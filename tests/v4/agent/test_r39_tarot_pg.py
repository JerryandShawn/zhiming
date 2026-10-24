import pytest
from datetime import datetime
from mingjing_core.timekit.clock import FrozenClock, set_clock, get_clock
from tools.eval.targets.v4_target import V4Target
from tools.eval.targets.v4_live import V4LiveTarget
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.schema import load_scenario


@pytest.mark.parametrize("draw_source", ["pick", "auto"])
def test_native_live_tarot_action_path(draw_source):
    case = execution_overlay(load_scenario("tools/eval/scenarios/TA01.yaml"))
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
            result.db = target.inspect_db()
            from tools.eval.judges import check_assertions

            assert all(c.passed for c in check_assertions(turn.expect.model_dump(exclude_none=True), result))
            if i == 2:
                assert result.metadata["prior_turns"][0]["receipts"]
    finally:
        target.close()
        set_clock(old)
