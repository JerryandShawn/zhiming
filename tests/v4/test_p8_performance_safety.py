"""Offline timing cannot silently drop effects or accept an unbounded run."""

import pytest

from mingjing_core.adapters.charts.benchmarks import night24_performance as performance


@pytest.mark.parametrize("repeats,warmups", [(0, 0), (21, 0), (1, -1), (1, 3)])
def test_invalid_sample_budget_is_rejected_before_engine_call(
    monkeypatch, repeats, warmups
):
    def forbidden(*args):
        raise AssertionError("invalid budget reached the chart engine")

    monkeypatch.setattr(performance, "measure_once", forbidden)
    with pytest.raises(ValueError, match="bounded_repeat"):
        performance.measure_system("bazi", "synthetic", repeats, warmups)


@pytest.mark.parametrize("field", ["model_calls", "writes"])
def test_effect_invariant_is_checked_even_for_discarded_warmup(monkeypatch, field):
    calls = 0

    def observed(*args):
        nonlocal calls
        calls += 1
        return {"model_calls": 0, "writes": 0} | {field: int(calls == 1)}

    monkeypatch.setattr(performance, "measure_once", observed)
    with pytest.raises(ValueError, match="readonly_effects"):
        performance.measure_system("bazi", "synthetic", repeats=1, warmups=1)


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")], [-1.0]])
def test_bad_clock_samples_cannot_receive_plausible_summary(values):
    with pytest.raises(ValueError, match="finite_nonnegative"):
        performance.summarize(values)


def test_cli_does_not_offer_live_mode():
    with pytest.raises(SystemExit) as error:
        performance.main(["--mode", "live"])
    assert error.value.code == 2
