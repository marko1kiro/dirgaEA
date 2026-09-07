"""BUILD 15 reference execution safety implementation."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List


class SpreadProfiler:
    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self.samples: List[float] = []

    def add_sample(self, spread: float):
        self.samples.append(spread)
        if len(self.samples) > self.window_size:
            self.samples.pop(0)

    def get_median(self) -> float:
        if not self.samples:
            return 10.0
        s = sorted(self.samples)
        mid = len(s) // 2
        return s[mid]


@dataclass
class SafetyResult:
    passed: bool
    fail_reason: str = ""
    spread_ratio: float = 1.0
    price_deviation_points: float = 0.0


class ExecutionSafetyGuard:
    def __init__(self, max_spread_ratio: float = 2.0, max_slippage_points: float = 10.0):
        self.max_spread_ratio = max_spread_ratio
        self.max_slippage_points = max_slippage_points

    def check_safety(
        self,
        current_spread: float,
        median_spread: float,
        planned_price: float,
        current_tick_price: float,
        point: float,
        order_check_retcode: int
    ) -> SafetyResult:
        # 1. Spread Spike Veto
        ratio = current_spread / median_spread if median_spread > 0 else 1.0
        if ratio > self.max_spread_ratio:
            return SafetyResult(passed=False, fail_reason="spread_spike_veto", spread_ratio=ratio)

        # 2. Price Slippage Deviation Guard
        dev_pts = abs(planned_price - current_tick_price) / point if point > 0 else 0.0
        if dev_pts > self.max_slippage_points:
            return SafetyResult(passed=False, fail_reason="slippage_deviation_exceeded", price_deviation_points=dev_pts)

        # 3. OrderCheck validation
        if order_check_retcode != 0:
            return SafetyResult(passed=False, fail_reason=f"order_check_failed_{order_check_retcode}")

        return SafetyResult(passed=True, spread_ratio=ratio, price_deviation_points=dev_pts)
