"""BUILD 16 reference models for the hardening audit fixes (H-1..H-3, M-1..M-5, L-1..L-7).

Python-parity models of the corrected MQL5 behavior. These model the FIXED
logic — tests assert the guards now behave as the audit requires.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional

# --- Constants mirroring the fixed SessionNewsEngine.mqh defines ---
NEWS_CALENDAR_TTL_SECONDS = 300
NEWS_CALENDAR_FAILURE_TTL_SECONDS = 120
NEWS_RECOVERY_LOOKBACK_SECONDS = 2700
NEWS_LOCK_WINDOW_SECONDS = 1800
NEWS_SHOCK_WINDOW_SECONDS = 900


class NewsState:
    CLEAR = "CLEAR"
    LOCK = "LOCK"
    SHOCK = "SHOCK"
    RECOVERY = "RECOVERY"
    UNKNOWN = "UNKNOWN"


def news_cache_valid(last_fetch_time: float, server_time: float,
                     ttl: float = NEWS_CALENDAR_TTL_SECONDS) -> bool:
    """H-1: cached calendar result is usable only within the short TTL."""
    return last_fetch_time > 0 and (server_time - last_fetch_time) < ttl


def failure_cache_valid(last_fetch_time: float, server_time: float) -> bool:
    """M-4: a failed fetch caches NEWS_UNKNOWN only for the short failure TTL."""
    return news_cache_valid(last_fetch_time, server_time,
                            NEWS_CALENDAR_FAILURE_TTL_SECONDS)


def classify_news_event(event_time: float, server_time: float) -> str:
    """LOCK/SHOCK/RECOVERY classification mirroring EvaluateNews windows."""
    diff = event_time - server_time
    if 0 <= diff <= NEWS_LOCK_WINDOW_SECONDS:
        return NewsState.LOCK
    if -NEWS_SHOCK_WINDOW_SECONDS <= diff < 0:
        return NewsState.SHOCK
    if -NEWS_RECOVERY_LOOKBACK_SECONDS <= diff < -NEWS_SHOCK_WINDOW_SECONDS:
        return NewsState.RECOVERY
    return NewsState.CLEAR


def calendar_query_window(server_time: float):
    """M-1: the MT5 calendar query must cover the full RECOVERY lookback."""
    return server_time - NEWS_RECOVERY_LOOKBACK_SECONDS, server_time + 1800


def check_gating_news(news_state: str, news_guard_required: bool = True):
    """M-3: CheckGating honors the NewsGuardRequired flag.

    Returns (allow_entry, block_reason).
    """
    if news_state == NewsState.UNKNOWN and news_guard_required:
        return False, "news_calendar_unavailable"
    if news_state == NewsState.LOCK:
        return False, "news_lock_pre_event"
    if news_state == NewsState.SHOCK:
        return False, "news_shock_post_event"
    return True, ""


# --- H-2: daily loss guard with a re-anchored baseline ---

def is_daily_loss_limit_reached(daily_start_equity: float, current_equity: float,
                                daily_net_pnl: float, max_daily_loss_pct: float,
                                consecutive_losses: int,
                                max_consecutive_losses: int) -> bool:
    """Mirrors IsDailyLossLimitReached with the H-2 fix: the caller re-anchors
    daily_start_equity at every day rollover (CheckAndResetDailyLedger)."""
    assert daily_start_equity > 0, "baseline must be anchored before the guard runs"
    floating_pnl = current_equity - daily_start_equity - daily_net_pnl
    total_loss = -(daily_net_pnl + floating_pnl)
    max_allowed_loss = daily_start_equity * (max_daily_loss_pct / 100.0)
    if total_loss >= max_allowed_loss:
        return True
    if consecutive_losses >= max_consecutive_losses:
        return True
    return False


# --- L-4: per-position streaks with breakeven reset ---

@dataclass
class DailyTradeRecord:
    position_id: int
    net_pnl: float


def recompute_streaks_from_ledger(trades: List[DailyTradeRecord]):
    """L-4: streaks derive from per-position grouped records; a breakeven
    trade resets the losing streak. Returns (consecutive_losses, winning_streak)."""
    consecutive_losses = 0
    winning_streak = 0
    for rec in reversed(trades):
        if rec.net_pnl < 0:
            if winning_streak > 0:
                break
            consecutive_losses += 1
        elif rec.net_pnl > 0:
            if consecutive_losses > 0:
                break
            winning_streak += 1
        else:
            consecutive_losses = 0
    return consecutive_losses, winning_streak


def ledger_net_pnl(profit: float, commission: float, swap: float, fee: float) -> float:
    """L-3: restart-time reconstruction must include DEAL_FEE like the live path."""
    return profit + commission + swap + fee


# --- M-5: risk percent resolution ---

def effective_risk_percent(risk_percent: float,
                           diagnostic_alias: float) -> float:
    """M-5: new RiskPercent input wins; the deprecated RiskDiagnosticPercent
    alias (-1.0 = unset) applies only when explicitly set by an old .set file."""
    if diagnostic_alias >= 0:
        return diagnostic_alias
    return risk_percent


# --- L-1: quality-gate spread veto ---

B09_MAX_SPREAD_RATIO = 0.25


def spread_veto_triggered(spread_price: float, stop_distance: float) -> bool:
    """L-1: NaN spread must trigger the veto (it must not be blessable)."""
    if not math.isfinite(spread_price):
        return True
    return spread_price > B09_MAX_SPREAD_RATIO * stop_distance


def spread_entry_allowed(spread_price: float) -> bool:
    """L-2: no valid quote => no entry (never fabricate a spread)."""
    return math.isfinite(spread_price) and spread_price > 0


# --- H-3: timeout-reconcile lifecycle ---

class Lifecycle:
    IDLE = "IDLE"
    ORDER_PENDING = "ORDER_PENDING"
    PARTIAL_FILL = "PARTIAL_FILL"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    TIMEOUT_RECONCILE = "TIMEOUT_RECONCILE"


@dataclass
class TimeoutResolver:
    """Python model of ResolveTimeoutState + the ExecuteIntent blocking guard."""
    lifecycle: str = Lifecycle.IDLE
    pending_order_ticket: int = 0
    pending_deal_ticket: int = 0

    def resolve_timeout_state(self, deal_in_history: bool,
                              order_history_state: Optional[str],
                              order_in_working_pool: bool) -> bool:
        """Returns True when the state reached a terminal resolution."""
        assert self.lifecycle == Lifecycle.TIMEOUT_RECONCILE
        # 1. positive proof of fill: deal in history
        if self.pending_deal_ticket > 0 and deal_in_history:
            self.lifecycle = Lifecycle.CONFIRMED
            self.pending_order_ticket = 0
            self.pending_deal_ticket = 0
            return True
        # 2. proof of no-fill: terminal non-filled order trace in history
        if self.pending_order_ticket > 0 and order_history_state is not None:
            if order_history_state in ("FILLED", "PARTIAL"):
                self.lifecycle = Lifecycle.CONFIRMED
            else:
                self.lifecycle = Lifecycle.REJECTED
            self.pending_order_ticket = 0
            self.pending_deal_ticket = 0
            return True
        # 3/4. still working or no trace anywhere -> stay blocked
        return False

    def execute_intent_allowed(self) -> bool:
        """H-3: ExecuteIntent must block while TIMEOUT_RECONCILE is unresolved."""
        return self.lifecycle != Lifecycle.TIMEOUT_RECONCILE
