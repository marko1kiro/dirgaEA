import pytest
from tests.build15.reference_execution_safety import (
    SpreadProfiler, ExecutionSafetyGuard, SafetyResult
)


def test_spread_spike_veto():
    profiler = SpreadProfiler(window_size=10)
    # Typical spread around 8-10 points
    for _ in range(9):
        profiler.add_sample(10.0)
    # Sudden spread spike to 25.0 points (> 2.0x median)
    profiler.add_sample(25.0)

    guard = ExecutionSafetyGuard(max_spread_ratio=2.0, max_slippage_points=10.0)
    res = guard.check_safety(
        current_spread=25.0,
        median_spread=profiler.get_median(),
        planned_price=1.1000,
        current_tick_price=1.1000,
        point=0.00001,
        order_check_retcode=0
    )
    assert res.passed is False
    assert res.fail_reason == "spread_spike_veto"


def test_slippage_deviation_veto():
    guard = ExecutionSafetyGuard(max_spread_ratio=2.0, max_slippage_points=10.0)
    # Planned entry at 1.1000, current price moved to 1.10015 (15 points deviation > 10 points)
    res = guard.check_safety(
        current_spread=10.0,
        median_spread=10.0,
        planned_price=1.1000,
        current_tick_price=1.10015,
        point=0.00001,
        order_check_retcode=0
    )
    assert res.passed is False
    assert res.fail_reason == "slippage_deviation_exceeded"

