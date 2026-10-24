"""R18 real PG and native wire with synthetic HTTP; never a real provider."""

import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.models.port import ToolSpec
from tools.eval import k31_connect
from tools.eval.k31_connect import ConnectionExecution, run_connection
from tools.eval.k31_contract import CASES
from tools.probe_equivalence_control import ProbeControlError

from .test_delegated_policy import CANDIDATE
from .test_delegated_quota_pg import central_fixture as central_fixture  # noqa: F401
from .test_k31_connection_pg import official_counter as original_counter
from .test_k31_connection_pg import setup
from .test_k31_first_release import registry
from .test_protocols import recording


@pytest.fixture(scope="module", name="official_counter")
def counter_fixture():
    return original_counter.__wrapped__()


@pytest.fixture
def variable_echo(monkeypatch):
    # Synthetic loop coverage permits varying arguments; the real fixed-value
    # schema is unchanged, so its identical repeated calls must still stop.
    echo = ToolSpec(
        "synthetic_echo",
        "synthetic",
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    monkeypatch.setattr(k31_connect, "CASES", (replace(CASES[0], tools=(echo,)), *CASES[1:]))


def transport(final_after, posted, *, repeat_at=None, bad_model_at=None, no_reasoning_at=None):
    def respond(request):
        body = json.loads(request.content)
        posted.append(body)
        turn = len(posted)
        assert body["model"] == "k3.1-pro" and body["reasoning_effort"] == "high"
        if 1 < turn <= final_after:
            assistant, tool = body["messages"][-2:]
            assert assistant["reasoning_content"] == "合成推理" + str(turn - 1)
            assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"]
            assert json.loads(tool["content"]) == json.loads(assistant["tool_calls"][0]["function"]["arguments"])
        delta = {} if turn == no_reasoning_at else {"reasoning_content": "合成推理" + str(turn)}
        if turn < final_after:
            value = turn - 1 if turn == repeat_at else turn
            delta["tool_calls"] = [
                {
                    "index": 0,
                    "id": "opaque-" + str(turn),
                    "function": {
                        "name": "synthetic_echo",
                        "arguments": json.dumps({"value": "合成" if value == 1 else "合成" + str(value)}),
                    },
                }
            ]
            finish = "tool_calls"
        else:
            delta["content"] = "合成故事。" * 300 + "[K31-END]" if turn == final_after + 2 else "合成"
            finish = "stop"
        return httpx.Response(
            200,
            content=recording(
                {
                    "model": "wrong" if turn == bad_model_at else "k3.1-pro",
                    "choices": [{"delta": delta, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 10000, "completion_tokens": 2000},
                }
            ),
        )

    return httpx.MockTransport(respond)


@pytest.mark.parametrize("final_after", [2, 3, 4])
def test_tool_loop_finishes_within_four_requests_and_replays_every_round(
    central, official_counter, final_after, variable_echo
):
    guard, _, control, session = setup(central)
    posted = []
    result = run_connection(
        registry(),
        session,
        control,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=transport(final_after, posted),
    )
    assert result["complete"] and result["model_calls"] == len(posted) == final_after + 2
    assert result["tool_rounds"] == final_after and result["additional_tool_calls"] == final_after - 2
    assert result["tool_call_requests"] == final_after - 1
    assert all(r["response_model"] == "k3.1-pro" and r["effort"] == "high" for r in result["records"])
    assert guard.status()["in_flight"] == 0


@pytest.mark.parametrize("repeat_at", [2, 3])
def test_equal_name_and_arguments_ignore_changed_call_id_and_stop_before_execution(
    central, official_counter, repeat_at, variable_echo
):
    guard, _, control, session = setup(central)
    posted = []
    result = run_connection(
        registry(),
        session,
        control,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=transport(5, posted, repeat_at=repeat_at),
    )
    assert not result["complete"] and result["model_calls"] == len(posted) == repeat_at
    assert result["records"][-1]["failure_reason"] == "repeated_identical_tool_call"
    assert result["additional_tool_calls"] == max(0, repeat_at - 2)


def test_fourth_tool_request_is_retained_as_failure_without_a_fifth_request(central, official_counter, variable_echo):
    guard, _, control, session = setup(central)
    posted = []
    result = run_connection(
        registry(),
        session,
        control,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=transport(5, posted),
    )
    assert not result["complete"] and result["model_calls"] == len(posted) == 4
    assert result["records"][-1]["failure_reason"] == "tool_round_limit"


@pytest.mark.parametrize("failure", ["identity", "reasoning"])
def test_later_round_still_checks_identity_and_reasoning(central, official_counter, failure, variable_echo):
    guard, _, control, session = setup(central)
    posted = []
    options = {"bad_model_at" if failure == "identity" else "no_reasoning_at": 3}
    result = run_connection(
        registry(),
        session,
        control,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=transport(4, posted, **options),
    )
    assert not result["complete"] and result["model_calls"] == len(posted) == 3
    assert result["stop_kind"] == ("permission_error" if failure == "identity" else None)


def test_twenty_call_guard_counts_old_candidate_attempts_before_any_new_post():
    authorization = "v7d-" + CANDIDATE + "-k31-connect-" + "a" * 32
    control = SimpleNamespace(physical=lambda _: [{"authorization_id": authorization}] * 20)
    execution = ConnectionExecution(None, SimpleNamespace(guard=None), control, "synthetic", None)
    with pytest.raises(ProbeControlError, match="20"):
        execution.step(CASES[0], 1, [])


def test_real_fixed_tool_contract_rejects_repeat_with_required_policy_visible(central, official_counter):
    guard, _, control, session = setup(central)
    posted = []
    result = run_connection(
        registry(),
        session,
        control,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=transport(5, posted, repeat_at=2),
    )
    assert not result["complete"] and len(posted) == result["model_calls"] == 2
    assert all(body["tool_choice"] == "required" for body in posted)
    assert result["records"][-1]["failure_reason"] == "repeated_identical_tool_call"


def test_new_control_retains_two_prior_calls_in_cumulative_twenty_limit(central, official_counter):
    guard, _, old, first = setup(central)
    posted = []
    failed = run_connection(
        registry(),
        first,
        old,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=transport(5, posted, repeat_at=2),
    )
    _, _, new, second = setup(central)
    completed = run_connection(
        registry(), second, new, K3EstimatedMeter(official_counter, model="k3.1-pro"), transport=transport(2, [])
    )
    assert completed["complete"] and completed["cumulative_model_calls"] == completed["model_calls"] == 6
    assert set(failed["attempt_ids"]) <= set(completed["attempt_ids"])
    assert set(failed["attempt_ids"]) <= set(completed["wasted_attempt_ids"])
