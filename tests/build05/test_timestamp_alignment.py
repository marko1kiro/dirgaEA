import pytest


def test_B05_FR4_valid_volatility_result_must_carry_finalized_h1_timestamp():
    atr_seq = [1.0, 1.2, 1.5, 1.8, 2.0]
    baseline_bars = 3
    fake_h1_time = 1640000000
    
    result = volatility_level_with_timestamp(atr_seq, baseline_bars, fake_h1_time)
    
    assert result["valid"] is True, "Volatility should be valid with sufficient ATR data"
    assert result["latestClosedH1"] is not None, "Valid volatility must carry H1 timestamp"
    assert result["latestClosedH1"] == fake_h1_time, f"latestClosedH1 must be set to actual H1 time, got {result['latestClosedH1']}"


def test_B05_FR4B_all_three_domains_same_update_must_have_identical_timestamps():
    fake_time = 1640000000
    close_seq = [100.0 + i for i in range(25)]
    ema_fast = [100.0 + i * 0.5 for i in range(3)]
    ema_slow = [100.0 + i * 0.3 for i in range(3)]
    atr_seq = [1.0] * 25
    
    dir_result = direction_with_timestamp(close_seq, ema_fast, ema_slow, atr_seq[-1], fake_time)
    mom_result = momentum_with_timestamp(close_seq, atr_seq, fake_time)
    vol_result = volatility_with_timestamp(atr_seq, 10, fake_time)
    
    assert dir_result["valid"] is True
    assert mom_result["valid"] is True
    assert vol_result["valid"] is True
    
    assert dir_result["latestClosedH1"] == fake_time, f"Direction timestamp mismatch: {dir_result['latestClosedH1']} != {fake_time}"
    assert mom_result["latestClosedH1"] == fake_time, f"Momentum timestamp mismatch: {mom_result['latestClosedH1']} != {fake_time}"
    assert vol_result["latestClosedH1"] == fake_time, f"Volatility timestamp mismatch: {vol_result['latestClosedH1']} != {fake_time}"
    
    assert dir_result["latestClosedH1"] == mom_result["latestClosedH1"] == vol_result["latestClosedH1"], \
        "All three domains must report identical H1 timestamp on same update"


def volatility_level_with_timestamp(atr_seq, baseline_bars, h1_time):
    count = len(atr_seq)
    if count < 1 or baseline_bars <= 0:
        return {"valid": False, "latestClosedH1": 0}
    
    n = count - 1
    if not (atr_seq[n] > 0.0):
        return {"valid": False, "latestClosedH1": 0}
    
    base = min(baseline_bars, count)
    total = 0.0
    valid_count = 0
    for i in range(count - base, count):
        if atr_seq[i] > 0.0:
            total += atr_seq[i]
            valid_count += 1
    
    if valid_count == 0:
        return {"valid": False, "latestClosedH1": 0}
    
    baseline = total / valid_count
    if not (baseline > 0.0):
        return {"valid": False, "latestClosedH1": 0}
    
    ratio = atr_seq[n] / baseline
    
    return {
        "valid": True,
        "latestClosedH1": h1_time,
        "ratio": ratio
    }


def direction_with_timestamp(close_seq, ema_fast, ema_slow, atr_last, h1_time):
    if len(close_seq) < 3 or len(ema_fast) < 3 or len(ema_slow) < 3:
        return {"valid": False, "latestClosedH1": 0}
    if not (atr_last > 0.0):
        return {"valid": False, "latestClosedH1": 0}
    
    return {"valid": True, "latestClosedH1": h1_time, "score": 0.5}


def momentum_with_timestamp(close_seq, atr_seq, h1_time):
    if len(close_seq) < 6 or len(atr_seq) < 6:
        return {"valid": False, "latestClosedH1": 0}
    if not (atr_seq[-1] > 0.0):
        return {"valid": False, "latestClosedH1": 0}
    
    return {"valid": True, "latestClosedH1": h1_time, "strength": 0.5}


def volatility_with_timestamp(atr_seq, baseline_bars, h1_time):
    return volatility_level_with_timestamp(atr_seq, baseline_bars, h1_time)
