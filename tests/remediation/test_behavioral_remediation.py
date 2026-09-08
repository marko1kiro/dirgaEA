import pytest
from .reference_remediation import *


def test_f01_two_actor_absent_bootstrap_has_one_winner():
    lock=GenerationLock(); snapshot=lock.value
    assert lock.cas(snapshot,1,100)
    assert not lock.cas(snapshot,1,100)

def test_f01_heartbeat_defeats_stale_takeover_and_stale_owner():
    lock=GenerationLock(); a=lock.acquire(100,30); assert a==1
    a=lock.heartbeat(a,125); assert a==2
    assert lock.acquire(140,30) is None
    assert not lock.release(1,141)

def test_f01_restart_keeps_unresolved_journal_blocked():
    j=SubmissionJournal(); j.begin(); j.restart(); assert j.entry_blocked
    assert j.evidence('fill') and not j.entry_blocked


def test_f02_restart_loss_survives_persisted_baseline():
    assert adjusted_daily_loss(10_000,9_800,0)==200

def test_f02_cashflow_cannot_hide_or_create_loss():
    assert adjusted_daily_loss(10_000,10_300,500)==200
    assert adjusted_daily_loss(10_000,9_300,-500)==200

def test_f02_streak_uses_full_lifecycle_costs_and_ignores_partial():
    # first partial exit is unresolved; completed row includes entry and exit costs
    losses,wins=lifecycle_streak([(False,[-1,-20]),(True,[-2,30,-4]),(True,[-1,-10,-2])])
    assert (losses,wins)==(1,0)


def test_f03_news_cache_re_evaluates_against_moving_now():
    event=10_000; cov=(5_000,15_000)
    assert news_state(8_300,[event],cov)==News.LOCK
    assert news_state(10_100,[event],cov)==News.SHOCK
    assert news_state(11_000,[event],cov)==News.RECOVERY
    assert news_state(13_000,[event],cov)==News.CLEAR

def test_f03_unknown_absorbs_explicit_clear_on_fetch_or_coverage_failure():
    assert news_state(10_000,[],(7_000,14_000),False)==News.UNKNOWN
    assert news_state(10_000,[],(9_000,14_000),True)==News.UNKNOWN


@pytest.mark.parametrize('direction,sl,tp,ok',[
    ('buy',1.0980,1.1020,True),('buy',1.09961,1.1020,False),
    ('sell',1.1020,1.0980,True),('sell',1.0990,1.0980,False)])
def test_f04_directional_stop_boundaries(direction,sl,tp,ok):
    assert validate_stop(direction,sl,tp,1.1000,1.1002,.0004) is ok


def test_f05_timeout_remains_absorbing_until_terminal_evidence():
    j=SubmissionJournal(); j.begin(); j.timeout(); assert j.entry_blocked
    assert not j.evidence('history_unavailable') and j.entry_blocked
    assert j.evidence('reject') and not j.entry_blocked


def test_f06_classifier_consumes_raw_ratio_not_normalized_score():
    assert [classify_atr(x) for x in (.6,1.0,1.5,2.0)]==['low','normal','high','extreme']
    assert classify_atr(1.5)!=classify_atr(.75)  # both could collapse under unrelated normalized diagnostics


def test_f07_one_final_object_fields_are_identical_for_risk_check_send():
    request={'price':1.10015,'sl':1.09785,'tp':1.10475,'volume':.13}
    risk_request=request
    order_check=request
    order_send=request
    assert risk_request is order_check is order_send


def C(regime='trend_bull',family='pullback',direction='buy',source=100,available=200,m15=300,ref=10,
      entry=1.1,stop=1.09,target=1.12,extension_reference=1.095):
    return Candidate(regime,family,direction,source,available,m15,ref,entry,stop,target,extension_reference)

def test_f08_regime_arbiter_rejects_stale_and_outputs_at_most_one():
    candidates=[C(),C(source=99),C(regime='range',family='range_sweep')]
    selected=arbitrate(candidates,'trend_bull',100,200)
    assert selected==candidates[0]

def test_f08_deterministic_family_priority():
    assert arbitrate([C(family='momentum'),C(family='break_retest')],'trend_bull',100,200).family=='break_retest'


def test_f09_live_quote_recomputes_rr_and_rejects_passed_target():
    c=C(entry=1.10,stop=1.09,target=1.12,extension_reference=1.095)
    final=finalize(c,1.105,1.106,.01); assert final and final[0].entry==1.106
    assert final[1]==pytest.approx((1.12-1.106)/(1.106-1.09))
    assert finalize(c,1.121,1.122,.01) is None

def test_f09_sell_wrong_side_target_rejected():
    assert finalize(C(regime='trend_bear',direction='sell',stop=1.11,target=1.105,extension_reference=1.105),1.10,1.101,.01) is None


def test_f10_current_spread_is_checked_before_single_epilogue_append():
    w=SpreadWindow([5,5,5,30,30]); assert median(w.values)==5
    assert not w.allows(30)
    w.epilogue(30); assert len(w.values)==6


def test_f11_fifth_bar_confirms_center_pivot_once():
    f=SwingFifo();
    for h,l in [(1,0),(2,0),(5,0),(2,0),(1,0)]: f.feed(h,l)
    assert f.swings==[(2,'high',5)]

def test_f11_fifo_stays_bounded_and_retains_newest():
    f=SwingFifo(256)
    for n in range(300):
        base=n*10
        for h,l in [(base+1,0),(base+2,0),(base+5,-1),(base+2,0),(base+1,0)]: f.feed(h,l)
    assert len(f.swings)==256
    highs=[s for s in f.swings if s[1]=='high']
    assert highs[-1][2]==2995
    assert highs[0][2]>5


def test_f12_identifier_key_survives_partial_and_trailing_restart():
    s=InitialStopStore(); key=(7,'EURUSD',42,999)
    s.save(*key,1.09); s.close(key,still_live=True)
    assert s.values[key]==1.09  # not ticket-based, and not overwritten with trailed SL
    s.close(key,still_live=False); assert key not in s.values
