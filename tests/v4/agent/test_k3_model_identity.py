"""Configured model identity survives reconstruction from calibrated factors."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.agent.context_types import InputMeterUnverified
from mingjing_core.application.agent_model_calls import RequestLedger

from .test_context_k3 import FixedCounter


@pytest.mark.parametrize("model", [None, "", "  ", 7])
def test_meter_refuses_empty_or_non_text_model_identity(model: str) -> None:
    with pytest.raises(InputMeterUnverified):
        K3EstimatedMeter(FixedCounter(10), model=model)


def test_request_ledger_preserves_configured_model_when_applying_calibration() -> None:
    identities = []

    def factor(owner, subject, thread, identity):
        identities.append((owner, subject, thread, identity.model))
        return "2.2"

    base = K3EstimatedMeter(FixedCounter(10), model="configured-k3-identity")
    ledger = object.__new__(RequestLedger)
    ledger.base_meter = base
    ledger.usage = SimpleNamespace(factor=factor)
    measured = ledger.meter({"owner": "alice", "subject": "self", "thread_id": "life:self", "request": {}})
    assert measured.model == base.model == "configured-k3-identity"
    assert measured.counter is base.counter and measured.estimate_multiplier == "2.2"
    assert identities == [("alice", "self", "life:self", "configured-k3-identity")]
