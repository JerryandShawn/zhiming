"""Keep committed answer bodies exact while removing one history metadata line."""

import pytest

from mingjing_core.application.agent_answer_text import without_history_header
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenario
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target


def test_native_committed_answer_removes_only_first_header():
    body = "你好。\n\n[2026-10-17T10:32:00+08:00 web]\n正文中的标记保持。"
    value = execution_overlay(load_scenario("tools/eval/scenarios/Q01.yaml")).model_dump(mode="json")
    value["scripted"] = [{"turn": 1, "model": [{"text": "[2026-10-17T10:32:00+08:00 web]\n" + body}]}]
    target = V4Target()
    try:
        evaluate_scenario(Scenario.model_validate(value), target, target_name="v4")
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert run["status"] == "succeeded"
        assert run["result"]["text"] == body
        message = target.repo.get(target.owner, "message", run["result"]["message_id"])
        assert message["content"] == body
    finally:
        target.close()


@pytest.mark.parametrize(
    "text",
    [
        "前文\n[2026-10-17T10:32:00+08:00 web]\n后文",
        "[2026-10-17T10:32:00+08:00 web] 同行正文",
        "[说明]\n正文",
    ],
)
def test_body_or_nonheader_is_unchanged(text):
    assert without_history_header(text) == text
