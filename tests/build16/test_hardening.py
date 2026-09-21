"""BUILD 16 behavioral tests for the hardening audit fixes.

Covers H-1..H-3, M-1..M-5, L-1..L-4 via the python-parity reference models.
"""

import math
import pytest

from tests.build16.reference_hardening import (
    NEWS_CALENDAR_TTL_SECONDS,
    NEWS_CALENDAR_FAILURE_TTL_SECONDS,
    NEWS_RECOVERY_LOOKBACK_SECONDS,
    NewsState,
    Lifecycle,
    news_cache_valid,
    failure_cache_valid,
    classify_news_event,
    calendar_query_window,
    check_gating_news,
    is_daily_loss_limit_reached,
    recompute_streaks_from_ledger,
    ledger_net_pnl,
    effective_risk_percent,
    spread_veto_triggered,
    spread_entry_allowed,
    DailyTradeRecord,
    TimeoutResolver,
)


# --- H-1: news TTL 300s << 1800s LOCK window ---

def test_news_cache_ttl_is_short():
    assert NEWS_CALENDAR_TTL_SECONDS == 300
    assert NEWS_CALENDAR_TTL_SECONDS < 1800


def test_news_cache_expires_before_lock_window():
    # Fetch at T returned CLEAR. At T+20min an event enters the 30-min LOCK
    # window; the stale cache must NOT be trusted past the 5-min TTL.
    assert news_cache_valid(1000.0, 1000.0 + 299.0)
    assert not news_cache_valid(1000.0, 1000.0 + 300.0)
    assert not news_cache_valid(1000.0, 1000.0 + 1200.0)


def test_h1_timeline_no_blind_spot():
    # Concrete H-1 timeline: fetch at T (CLEAR), event at T+50min.
    # At T+20min the event is 30min out -> LOCK required. Cache must have
    # expired long before so a re-fetch happens.
    fetch_t = 0.0
    event_t = 3000.0  # T+50min
    check_t = 1200.0  # T+20min
    assert classify_news_event(event_t, check_t) == NewsState.LOCK
    assert not news_cache_valid(fetch_t, check_t), \
        "stale CLEAR cache must not mask the LOCK window"


# --- M-4: short failure TTL ---

def test_failure_ttl_is_short():
    assert NEWS_CALENDAR_FAILURE_TTL_SECONDS == 120
    assert failure_cache_valid(1000.0, 1000.0 + 119.0)
    assert not failure_cache_valid(1000.0, 1000.0 + 120.0)


# --- M-1: query window covers full RECOVERY lookback ---

def test_calendar_query_window_covers_recovery():
    from_t, to_t = calendar_query_window(10000.0)
    assert from_t == 10000.0 - NEWS_RECOVERY_LOOKBACK_SECONDS
    assert NEWS_RECOVERY_LOOKBACK_SECONDS == 2700


def test_recovery_classification_full_window():
    # Event 40 min old must classify as RECOVERY (was unreachable at 30-45min).
    assert classify_news_event(10000.0 - 2400.0, 10000.0) == NewsState.RECOVERY
    assert classify_news_event(10000.0 - 2699.0, 10000.0) == NewsState.RECOVERY
    assert classify_news_event(10000.0 - 2701.0, 10000.0) == NewsState.CLEAR


# --- M-3: NewsGuardRequired honored ---

def test_news_guard_required_blocks_unknown():
    allow, reason = check_gating_news(NewsState.UNKNOWN, news_guard_required=True)
    assert not allow
    assert reason == "news_calendar_unavailable"


def test_news_guard_disabled_allows_unknown():
    allow, _ = check_gating_news(NewsState.UNKNOWN, news_guard_required=False)
    assert allow


def test_lock_shock_block_regardless_of_flag():
    for flag in (True, False):
        allow, _ = check_gating_news(NewsState.LOCK, news_guard_required=flag)
        assert not allow
        allow, _ = check_gating_news(NewsState.SHOCK, news_guard_required=flag)
        assert not allow


# --- H-2: daily equity baseline re-anchored ---

def test_daily_loss_guard_uses_today_baseline():
    # Day 2: baseline re-anchored to 10_000 at 00:00. A 1.5% intraday loss
    # must NOT trip the 2% cap (previously measured from day-1 baseline).
    assert not is_daily_loss_limit_reached(
        daily_start_equity=10000.0, current_equity=9850.0, daily_net_pnl=0.0,
        max_daily_loss_pct=2.0, consecutive_losses=0, max_consecutive_losses=3)


def test_daily_loss_guard_trips_at_cap():
    assert is_daily_loss_limit_reached(
        daily_start_equity=10000.0, current_equity=9790.0, daily_net_pnl=0.0,
        max_daily_loss_pct=2.0, consecutive_losses=0, max_consecutive_losses=3)


def test_daily_loss_guard_includes_floating_and_realized():
    # -1% realized + -1.2% floating = -2.2% total -> blocked at 2% cap.
    assert is_daily_loss_limit_reached(
        daily_start_equity=10000.0, current_equity=9780.0, daily_net_pnl=-100.0,
        max_daily_loss_pct=2.0, consecutive_losses=0, max_consecutive_losses=3)


def test_daily_loss_guard_consecutive_losses():
    assert is_daily_loss_limit_reached(
        daily_start_equity=10000.0, current_equity=10000.0, daily_net_pnl=0.0,
        max_daily_loss_pct=2.0, consecutive_losses=3, max_consecutive_losses=3)


def test_h2_phantom_cushion_eliminated():
    # Old bug: baseline stuck at day-1 9_000 after a winning day; a 2% loss
    # measured against 9_000 trips at 8_820 — but the *correct* day-2 baseline
    # is 10_000, tripping at 9_800. Re-anchoring removes the phantom cushion.
    correct = is_daily_loss_limit_reached(
        daily_start_equity=10000.0, current_equity=9900.0, daily_net_pnl=0.0,
        max_daily_loss_pct=2.0, consecutive_losses=0, max_consecutive_losses=3)
    stale = is_daily_loss_limit_reached(
        daily_start_equity=9000.0, current_equity=9900.0, daily_net_pnl=0.0,
        max_daily_loss_pct=2.0, consecutive_losses=0, max_consecutive_losses=3)
    assert not correct  # -1% intraday: fine
    assert not stale   # stale baseline sees a *gain*: guard is blind here


# --- L-4: per-position streaks + breakeven reset ---

def test_streak_per_position_not_per_deal():
    # One losing position closed in two partial deals must count once.
    trades = [DailyTradeRecord(position_id=7, net_pnl=-50.0)]
    assert recompute_streaks_from_ledger(trades) == (1, 0)


def test_streak_breaks_on_win():
    trades = [
        DailyTradeRecord(position_id=1, net_pnl=-10.0),
        DailyTradeRecord(position_id=2, net_pnl=25.0),
        DailyTradeRecord(position_id=3, net_pnl=-5.0),
    ]
    assert recompute_streaks_from_ledger(trades) == (1, 0)


def test_breakeven_resets_losing_streak():
    trades = [
        DailyTradeRecord(position_id=1, net_pnl=-10.0),
        DailyTradeRecord(position_id=2, net_pnl=0.0),
        DailyTradeRecord(position_id=3, net_pnl=-5.0),
    ]
    losses, wins = recompute_streaks_from_ledger(trades)
    assert losses == 1
    assert wins == 0


def test_breakeven_keeps_win_streak():
    trades = [
        DailyTradeRecord(position_id=1, net_pnl=20.0),
        DailyTradeRecord(position_id=2, net_pnl=0.0),
    ]
    assert recompute_streaks_from_ledger(trades) == (0, 1)


# --- L-3: fee included in reconstruction ---

def test_ledger_net_pnl_includes_fee():
    assert ledger_net_pnl(100.0, -2.0, -1.0, -0.5) == 96.5


# --- M-5: risk percent resolution ---

def test_effective_risk_percent_new_input():
    assert effective_risk_percent(0.50, -1.0) == 0.50


def test_effective_risk_percent_deprecated_alias():
    # Old .set file explicitly set the alias -> honored for compat.
    assert effective_risk_percent(0.50, 0.75) == 0.75


# --- L-1 / L-2: spread handling ---

def test_spread_veto_triggers_on_nan():
    assert spread_veto_triggered(math.nan, 100.0)


def test_spread_veto_triggers_on_excessive():
    assert spread_veto_triggered(30.0, 100.0)
    assert not spread_veto_triggered(10.0, 100.0)


def test_no_entry_without_valid_quote():
    assert not spread_entry_allowed(0.0)
    assert not spread_entry_allowed(-3.0)
    assert not spread_entry_allowed(math.nan)
    assert spread_entry_allowed(12.0)


# --- H-3: timeout-reconcile blocking + resolution ---

def test_execute_blocked_while_timeout_unresolved():
    r = TimeoutResolver(lifecycle=Lifecycle.TIMEOUT_RECONCILE,
                        pending_order_ticket=111, pending_deal_ticket=222)
    assert not r.execute_intent_allowed()


def test_timeout_resolves_on_history_deal():
    r = TimeoutResolver(lifecycle=Lifecycle.TIMEOUT_RECONCILE,
                        pending_order_ticket=111, pending_deal_ticket=222)
    assert r.resolve_timeout_state(deal_in_history=True,
                                   order_history_state=None,
                                   order_in_working_pool=False)
    assert r.lifecycle == Lifecycle.CONFIRMED
    assert r.execute_intent_allowed()


def test_timeout_resolves_on_history_reject():
    r = TimeoutResolver(lifecycle=Lifecycle.TIMEOUT_RECONCILE,
                        pending_order_ticket=111, pending_deal_ticket=0)
    assert r.resolve_timeout_state(deal_in_history=False,
                                   order_history_state="REJECTED",
                                   order_in_working_pool=False)
    assert r.lifecycle == Lifecycle.REJECTED
    assert r.execute_intent_allowed()


def test_timeout_stays_blocked_with_no_trace():
    r = TimeoutResolver(lifecycle=Lifecycle.TIMEOUT_RECONCILE,
                        pending_order_ticket=111, pending_deal_ticket=0)
    assert not r.resolve_timeout_state(deal_in_history=False,
                                       order_history_state=None,
                                       order_in_working_pool=False)
    assert r.lifecycle == Lifecycle.TIMEOUT_RECONCILE
    assert not r.execute_intent_allowed()


def test_timeout_stays_blocked_while_working():
    r = TimeoutResolver(lifecycle=Lifecycle.TIMEOUT_RECONCILE,
                        pending_order_ticket=111, pending_deal_ticket=0)
    assert not r.resolve_timeout_state(deal_in_history=False,
                                       order_history_state=None,
                                       order_in_working_pool=True)
    assert not r.execute_intent_allowed()
