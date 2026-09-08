"""Static contracts bind behavioral specs to production wiring.

They prove source topology/API consistency only, not MetaEditor or broker behavior.
"""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
def src(name): return (ROOT/name).read_text()


def test_f01_versioned_cas_lock_and_persistent_journal_contract():
    s=src('ExecutionBridge.mqh')
    assert 'GlobalVariableTemp(LockKey())' in s
    assert 'GlobalVariableSetOnCondition(LockKey(),replacement,expected)' in s
    assert 'RenewOrderLock()' in s and 'm_lockGeneration+1.0' in s
    assert 'DIRGA_PENDING_UNRESOLVED' in s and 'DIRGA_PENDING_TIMEOUT' in s
    assert 'RecoverPendingSubmission()' in s and 'GlobalVariablesFlush();' in s


def test_f02_persisted_account_day_ledger_replaces_resettable_out_deal_arithmetic():
    ledger=src('DailyRiskLedger.mqh'); ea=src('AdaptiveSurvivalEA.mq5')
    assert 'AccountInfoInteger(ACCOUNT_LOGIN)' in ledger and 'ServerFingerprint()' in ledger
    assert 'm_baselineEquity-adjusted' in ledger and 'm_externalCashflow' in ledger
    assert 'PositionStillLive(id)) continue' in ledger
    assert 'DEAL_COMMISSION' in ledger and 'DEAL_SWAP' in ledger and 'DEAL_FEE' in ledger
    for obsolete in ('daily_net_pnl','daily_start_equity','IsDailyLossLimitReached','consecutive_losses'):
        assert obsolete not in ea
    assert 'daily_ledger.AllowsNewEntry' in ea


def test_f03_event_time_cache_currency_filter_and_absorbing_unknown():
    s=src('SessionNewsEngine.mqh')
    assert 'CachedNewsEvent' in s and 's_coverageFrom' in s and 's_coverageTo' in s
    assert 'CalendarValueHistory(values,fromTime,toTime,NULL,currency)' in s
    assert 'CalendarEventById' in s
    assert 'current==NEWS_UNKNOWN || candidate==NEWS_UNKNOWN' in s
    assert 'EvaluateTimes(serverTime,times,n)' in s
    ea=src('AdaptiveSurvivalEA.mq5')
    assert 'gatedNews=NewsGuardRequired?observedNews:NEWS_CLEAR' in ea


def test_f04_position_direction_identity_and_raw_sltp_request():
    types=src('Types.mqh'); bridge=src('ExecutionBridge.mqh'); pm=src('PositionManager.mqh')
    assert re.search(r'struct PositionManageIntent\s*\{[^}]*ENUM_TRADE_DIRECTION\s+direction',types,re.S)
    assert 'actual!=intent.direction' in bridge
    assert 'request.action=TRADE_ACTION_SLTP' in bridge and 'request.position=intent.ticket' in bridge
    assert 'ValidateStopFreeze(intent.direction' in bridge
    assert 'outIntent.direction = dir' in pm


def test_f05_timeout_and_recovery_states_continue_reconciliation_and_block_entry():
    s=src('ExecutionBridge.mqh'); ea=src('AdaptiveSurvivalEA.mq5')
    block=s[s.index('bool EntrySubmissionBlocked()'):s.index('bool RecoverPendingSubmission()')]
    assert 'EXEC_LIFECYCLE_TIMEOUT_RECONCILE' in block and 'EXEC_LIFECYCLE_RECOVERY_BLOCKED' in block
    reconcile=s[s.index('void ReconcilePending()'):s.index('bool ExecutePositionManage')]
    assert 'DIRGA_PENDING_TIMEOUT' in reconcile and 'HistorySelect' in reconcile
    assert 'if(b10_execution_bridge.EntrySubmissionBlocked())' in ea
    assert 'b10_execution_bridge.ReconcilePending()' in ea


def test_f06_raw_atr_ratio_is_classifier_input_and_level_score_is_diagnostic():
    types=src('Types.mqh'); brain=src('MarketBrain.mqh')
    assert 'double atrRatio;' in types and 'double levelScore;' in types
    assert 'out.atrRatio = ratio' in brain
    assert re.search(r'VolatilityLevelClassify\([^;]*volatility\.atrRatio',brain,re.S)


def test_f07_single_final_request_object_is_risk_check_and_send_input():
    bridge=src('ExecutionBridge.mqh'); safety=src('ExecutionSafety.mqh'); ea=src('AdaptiveSurvivalEA.mq5')
    assert 'outPlan.riskRequest.entryPrice=outPlan.request.price' in bridge
    assert 'outPlan.riskRequest.stopLossPrice=outPlan.request.sl' in bridge
    assert 'outPlan.request.volume=outPlan.risk.normalizedVolume' in bridge
    assert 'outPlan.request.price=cand.entryPrice' in bridge and 'outPlan.request.sl=cand.initialStopPrice' in bridge
    assert 'OrderCheck(plan.request,check)' in safety and 'OrderSend(plan.request,outResult)' in bridge
    assert 'BuildFinalMarketOrder(finalCandidate' in ea and 'ValidateFinalOrder(plan' in ea and 'SendFinalMarketOrder(plan' in ea
    assert all(x not in ea for x in ('PrepareMarketOrder(','ValidateOrder(','ExecuteIntent('))


def test_f08_one_feed_shared_snapshot_regime_arbiter_and_one_dispatch():
    ea=src('AdaptiveSurvivalEA.mq5')
    assert ea.count('b07_trend_strategy.FeedM15Bar(')==1
    assert ea.count('b07_trend_strategy.GetM15Swings(')==2  # entry snapshot + management snapshot
    assert 'b11_range_strategy.Evaluate' in ea and 'b12_breakout_strategy.Evaluate' in ea
    assert 'SelectActiveCandidate(trend,hasTrend,range,hasRange,breakout,hasBreakout,selected)' in ea
    assert ea.count('SendFinalMarketOrder(')==1


def test_f09_retest_trigger_provenance_and_live_final_geometry():
    types=src('Types.mqh'); trend=src('TrendStrategy.mqh'); ea=src('AdaptiveSurvivalEA.mq5')
    for field in ('triggerBarTime','triggerAvailableAt','triggerOpen','triggerHigh','triggerLow','triggerClose'):
        assert field in types and field in trend
    assert 'm_pendingBreak.triggerAvailableAt!=now' in trend
    assert 'BuildFinalEntryCandidate(selected' in ea
    assert ea.index('BuildFinalEntryCandidate(selected') < ea.index('b09_quality_gate.Evaluate(finalCandidate')
    assert 'target_passed_or_wrong_side' in ea and 'out.rewardRiskRatio=out.rewardDistance/out.stopDistance' in ea


def test_f10_historical_spread_is_validated_then_appended_once_in_tick_epilogue():
    safety=src('ExecutionSafety.mqh'); ea=src('AdaptiveSurvivalEA.mq5')
    validate=safety[safety.index('bool ValidateFinalOrder'):]
    assert 'median=GetMedianSpread()' in validate and 'spread_spike_veto' in validate
    assert ea.count('FinalizeOnTickSample(broker_environment)')==1
    assert 'AddSpreadSample(' not in ea
    assert ea.index('ProcessCompletedM15Bar(completedH1Time)') < ea.index('FinalizeOnTickSample(broker_environment)')


def test_f11_incremental_center_pivot_and_true_swing_fifo():
    s=src('TrendStrategy.mqh')
    detect=s[s.index('void CTrendStrategy::DetectPivots()'):s.index('void CTrendStrategy::UpdateLegs')]
    assert 'int p=m_barsCount-3' in detect and 'm_bars[p+2]' in detect
    append=s[s.index('void CTrendStrategy::AppendSwing'):s.index('// Detect exactly')]
    assert 'm_swings[i-1]=m_swings[i]' in append and 'B07_MAX_SWINGS-1' in append
    assert 'm_breaksCount = 0' in s and 'm_lastCandidateIdentity=""' in s


def test_f12_identifier_stop_store_partial_retention_and_unprotected_policy():
    store=src('InitialStopStore.mqh'); ea=src('AdaptiveSurvivalEA.mq5'); bridge=src('ExecutionBridge.mqh')
    assert 'positionId' in store and 'POSITION_IDENTIFIER' in store
    assert 'PositionIsLive(positionId)' in store
    assert 'initial_stop_store.Load(positionId,initialSl)' in ea
    assert 'never reconstruct initial risk' in ea
    assert 'if(sl<=0.0)' in ea and 'unprotected_position_present=true' in ea
    assert 'unprotected_position_fail_closed' in ea
    assert 'PersistInitialStopForDeal' in bridge
    assert 'RemoveIfFullyClosed(positionId)' in ea


def test_related_h1_availability_precedes_management_and_m15_selection():
    ea=src('AdaptiveSurvivalEA.mq5')
    tick=ea[ea.index('void OnTick()'):ea.index('void OnTimer()')]
    assert tick.index('UpdateH1RegimeFusion()') < tick.index('ManageOpenPositions()') < tick.index('ProcessCompletedM15Bar')
    assert 'b06_result_available_at=TimeCurrent()' in tick
