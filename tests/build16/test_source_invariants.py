"""BUILD 16 source invariants — assert every hardening fix is present in the MQL5 source.

Follows the tests/build05/test_source_invariants.py convention: parse the
.mqh/.mq5 text and assert the exact code patterns the audit fixes require.
"""

import os
import re

import pytest

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_source(name):
    path = os.path.join(SOURCE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# --- H-1: news TTL ---

def test_h1_news_calendar_ttl_300():
    src = read_source("SessionNewsEngine.mqh")
    m = re.search(r"#define\s+NEWS_CALENDAR_TTL_SECONDS\s+(\d+)", src)
    assert m, "NEWS_CALENDAR_TTL_SECONDS define not found"
    assert int(m.group(1)) == 300, "TTL must be 300 s (H-1), got %s" % m.group(1)


# --- M-4: failure TTL ---

def test_m4_failure_ttl_defined_and_used():
    src = read_source("SessionNewsEngine.mqh")
    m = re.search(r"#define\s+NEWS_CALENDAR_FAILURE_TTL_SECONDS\s+(\d+)", src)
    assert m and int(m.group(1)) <= 120
    assert "NEWS_CALENDAR_TTL_SECONDS - NEWS_CALENDAR_FAILURE_TTL_SECONDS" in src, \
        "failure path must shorten the cached UNKNOWN lifetime (M-4)"


# --- M-1: recovery lookback ---

def test_m1_recovery_lookback_query():
    src = read_source("SessionNewsEngine.mqh")
    m = re.search(r"#define\s+NEWS_RECOVERY_LOOKBACK_SECONDS\s+(\d+)", src)
    assert m and int(m.group(1)) == 2700
    assert re.search(r"fromTime\s*=\s*serverTime\s*-\s*NEWS_RECOVERY_LOOKBACK_SECONDS", src), \
        "calendar query must use the recovery lookback (M-1)"


# --- M-2: country fail-closed ---

def test_m2_country_resolve_fail_closed():
    src = read_source("SessionNewsEngine.mqh")
    block = re.search(
        r"if\s*\(\s*!CalendarCountryById\(event\.country_id,\s*country\)\s*\)\s*\{(.*?)\}",
        src, re.DOTALL)
    assert block, "country-resolve branch not found"
    assert "NEWS_UNKNOWN" in block.group(1), \
        "country resolution failure must aggregate NEWS_UNKNOWN (M-2)"


# --- M-3: NewsGuardRequired honored in CheckGating ---

def test_m3_check_gating_honors_flag():
    src = read_source("SessionNewsEngine.mqh")
    assert re.search(r"CheckGating\(.*bool\s+newsGuardRequired", src), \
        "CheckGating must take a newsGuardRequired parameter (M-3)"
    assert "news == NEWS_UNKNOWN && newsGuardRequired" in src, \
        "NEWS_UNKNOWN block must be conditional on the flag (M-3)"


def test_m3_ea_passes_flag_no_unconditional_block():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert "CheckGating(sessionState, newsState, requiredQualityScore, gatingBlockReason, NewsGuardRequired)" in src
    assert "TRADE_BLOCKED_CALENDAR" not in src, \
        "redundant pre-check must be removed; gating is the single choke point (M-3)"


# --- M-5: RiskPercent rename + deprecated alias ---

def test_m5_risk_percent_input_with_alias():
    src = read_source("Config.mqh")
    assert re.search(r"input\s+double\s+RiskPercent\s*=\s*0\.50", src), \
        "RiskPercent input missing (M-5)"
    assert re.search(r"input\s+double\s+RiskDiagnosticPercent\s*=\s*-1\.0", src), \
        "deprecated RiskDiagnosticPercent alias missing (M-5)"
    ea = read_source("AdaptiveSurvivalEA.mq5")
    assert "EffectiveRiskPercent()" in ea
    assert ea.count("riskPercent = EffectiveRiskPercent()") == 2, \
        "both sizing paths (diagnostic + live) must use the resolver (M-5)"
    assert "riskPercent = RiskDiagnosticPercent" not in ea


# --- H-2: daily equity re-anchor ---

def test_h2_daily_start_equity_reanchored():
    src = read_source("AdaptiveSurvivalEA.mq5")
    m = re.search(r"void\s+CheckAndResetDailyLedger\s*\(\s*\)\s*\{(.*?)\n\}", src, re.DOTALL)
    assert m, "CheckAndResetDailyLedger not found"
    body = m.group(1)
    assert "ReconstructDailyLedger();" in body
    assert "daily_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);" in body, \
        "baseline must be re-anchored on day rollover (H-2)"


# --- H-3: timeout-reconcile resolution + blocking ---

def test_h3_resolve_timeout_state_exists():
    src = read_source("ExecutionBridge.mqh")
    assert "bool                    ResolveTimeoutState();" in src
    assert "bool CExecutionBridge::ResolveTimeoutState()" in src
    assert "HistoryDealSelect(m_pendingDealTicket)" in src
    assert "HistoryOrderSelect(m_pendingOrderTicket)" in src


def test_h3_execute_intent_blocks_on_timeout():
    src = read_source("ExecutionBridge.mqh")
    m = re.search(r"bool CExecutionBridge::ExecuteIntent\(.*?^\}", src, re.DOTALL | re.MULTILINE)
    assert m, "ExecuteIntent body not found"
    body = m.group(0)
    assert "EXEC_LIFECYCLE_TIMEOUT_RECONCILE" in body
    assert "EXECUTION_BLOCKED_TIMEOUT_UNRESOLVED" in body
    assert "return false;" in body


def test_h3_reconcile_pending_handles_timeout():
    src = read_source("ExecutionBridge.mqh")
    m = re.search(r"void CExecutionBridge::ReconcilePending\(\)\s*\{(.*?)\n\}", src, re.DOTALL)
    assert m, "ReconcilePending body not found"
    body = m.group(1)
    assert "EXEC_LIFECYCLE_TIMEOUT_RECONCILE" in body, \
        "ReconcilePending must no longer early-return on the timeout state (H-3)"
    assert "ResolveTimeoutState();" in body


# --- L-1: NaN spread veto ---

def test_l1_nan_spread_veto():
    src = read_source("QualityGate.mqh")
    assert "!MathIsValidNumber(currentSpreadPrice)" in src, \
        "spread veto must reject NaN (L-1)"


# --- L-2: no fabricated spread ---

def test_l2_no_fabricated_spread():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert "currentSpreadPrice = 10 * broker_environment.point" not in src, \
        "fabricated 10-point spread must be gone (L-2)"
    assert "TRADE_BLOCKED_NO_QUOTE" in src


# --- L-3: DEAL_FEE in reconstruction ---

def test_l3_fee_in_reconstruct():
    src = read_source("AdaptiveSurvivalEA.mq5")
    m = re.search(r"void\s+ReconstructDailyLedger\s*\(\s*\)\s*\{(.*?)\n\}", src, re.DOTALL)
    assert m, "ReconstructDailyLedger body not found"
    body = m.group(1)
    assert "DEAL_FEE" in body, "reconstruction must include DEAL_FEE (L-3)"
    assert "profit + commission + swap + fee" in body


# --- L-4: per-position streaks + breakeven ---

def test_l4_shared_streak_function():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert "void RecomputeStreaksFromLedger()" in src
    assert src.count("RecomputeStreaksFromLedger();") >= 2, \
        "both reconstruct and live paths must use the shared streak function (L-4)"


# --- L-5: genuine quote re-verification ---

def test_l5_drift_check_refetches():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert "QUOTE_REFRESH_FAILED" in src
    assert "SAME immutable tick" not in src, \
        "vacuous same-snapshot drift check must be gone (L-5)"


# --- L-6: PositionSelectByTicket ---

def test_l6_position_select_before_modify():
    src = read_source("ExecutionBridge.mqh")
    start = src.find("if (intent.action == POS_ACTION_MODIFY_SL)")
    assert start != -1, "MODIFY_SL branch not found"
    window = src[start:start + 2000]
    sel = window.find("PositionSelectByTicket(intent.ticket)")
    get = window.find("PositionGetInteger(POSITION_TYPE)")
    assert sel != -1 and get != -1, "L-6: PositionSelectByTicket missing in MODIFY_SL branch"
    assert sel < get, \
        "must select the ticket before reading POSITION_TYPE (L-6)"


# --- L-7: dead re-entrancy branch removed ---

def test_l7_no_dead_reentrancy_branch():
    src = read_source("ExecutionBridge.mqh")
    m = re.search(r"bool CExecutionBridge::AcquireOrderLock\(.*?^\}", src, re.DOTALL | re.MULTILINE)
    assert m, "AcquireOrderLock body not found"
    body = m.group(0)
    assert "Re-entrant: already our token" not in body, \
        "dead re-entrancy branch must be removed (L-7)"
    assert "currentOwner == m_ownerToken" not in body
