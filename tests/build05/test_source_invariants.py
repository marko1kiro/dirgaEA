import re
import pytest
import os


SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_source_reset_h1_brain_invalid_explicit_defaults():
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    func_match = re.search(r"void\s+ResetH1BrainInvalid\s*\(\s*H1BrainResult\s*&\s*brain\s*\)", source)
    assert func_match, "ResetH1BrainInvalid function not found"

    func_start = func_match.start()
    brace_count = 0
    func_end = func_start
    in_func = False
    for i, c in enumerate(source[func_start:], func_start):
        if c == "{":
            brace_count += 1
            in_func = True
        elif c == "}":
            brace_count -= 1
            if brace_count == 0 and in_func:
                func_end = i + 1
                break

    func_body = source[func_start:func_end]

    assert "brain.direction.state = DIRECTION_NEUTRAL" in func_body, \
        "Direction state must be explicitly DIRECTION_NEUTRAL"
    assert "brain.direction.score = 0" in func_body or "brain.direction.score = 0.0" in func_body, \
        "Direction score must be explicitly 0"
    assert "brain.direction.valid = false" in func_body, \
        "Direction valid must be explicitly false"

    assert "brain.momentum.state = MOMENTUM_NORMAL" in func_body, \
        "Momentum state must be explicitly MOMENTUM_NORMAL"
    assert "brain.momentum.strengthScore = 0" in func_body or "brain.momentum.strengthScore = 0.0" in func_body, \
        "Momentum strengthScore must be explicitly 0"
    assert "brain.momentum.valid = false" in func_body, \
        "Momentum valid must be explicitly false"
    assert "brain.momentum.helperDegraded = false" in func_body, \
        "Momentum helperDegraded must be explicitly false"

    assert "brain.volatility.level = VOL_NORMAL" in func_body, \
        "Volatility level must be explicitly VOL_NORMAL"
    assert "brain.volatility.quality = VOLQ_HEALTHY" in func_body, \
        "Volatility quality must be explicitly VOLQ_HEALTHY"
    assert "brain.volatility.valid = false" in func_body, \
        "Volatility valid must be explicitly false"


def test_source_caller_resets_before_copyrates_early_return():
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    update_func = re.search(r"void\s+UpdateH1Brain\s*\(\s*\)", source)
    assert update_func, "UpdateH1Brain function not found"

    func_start = update_func.start()
    brace_count = 0
    func_end = func_start
    in_func = False
    for i, c in enumerate(source[func_start:], func_start):
        if c == "{":
            brace_count += 1
            in_func = True
        elif c == "}":
            brace_count -= 1
            if brace_count == 0 and in_func:
                func_end = i + 1
                break

    func_body = source[func_start:func_end]

    reset_call_match = re.search(r"ResetH1BrainInvalid\s*\(\s*h1_brain\s*\)", func_body)
    assert reset_call_match, "ResetH1BrainInvalid(h1_brain) call not found in UpdateH1Brain"

    early_return_match = re.search(r"if\s*\(\s*copiedRates\s*<\s*3\s*\)\s*return", func_body)
    assert early_return_match, "CopyRates early return check not found"

    assert reset_call_match.start() < early_return_match.start(), \
        "ResetH1BrainInvalid must be called BEFORE CopyRates early return check"


def test_source_direction_persistence_guarded_by_valid():
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    update_func = re.search(r"void\s+UpdateH1Brain\s*\(\s*\)", source)
    assert update_func, "UpdateH1Brain function not found"

    func_start = update_func.start()
    brace_count = 0
    func_end = func_start
    in_func = False
    for i, c in enumerate(source[func_start:], func_start):
        if c == "{":
            brace_count += 1
            in_func = True
        elif c == "}":
            brace_count -= 1
            if brace_count == 0 and in_func:
                func_end = i + 1
                break

    func_body = source[func_start:func_end]

    direction_block = re.search(
        r"DirectionEngine\s*\([^)]+\)\s*;\s*"
        r"if\s*\(\s*h1_brain\.direction\.valid\s*\)\s*\{[^}]*DirectionClassify",
        func_body, re.DOTALL
    )
    assert direction_block, \
        "DirectionClassify must be inside if(h1_brain.direction.valid) guard"


def test_source_momentum_persistence_guarded_by_valid():
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    update_func = re.search(r"void\s+UpdateH1Brain\s*\(\s*\)", source)
    assert update_func, "UpdateH1Brain function not found"

    func_start = update_func.start()
    brace_count = 0
    func_end = func_start
    in_func = False
    for i, c in enumerate(source[func_start:], func_start):
        if c == "{":
            brace_count += 1
            in_func = True
        elif c == "}":
            brace_count -= 1
            if brace_count == 0 and in_func:
                func_end = i + 1
                break

    func_body = source[func_start:func_end]

    momentum_block = re.search(
        r"MomentumEngine\s*\([^)]+\)\s*;\s*"
        r"if\s*\(\s*h1_brain\.momentum\.valid\s*\)\s*\{[^}]*MomentumClassify",
        func_body, re.DOTALL
    )
    assert momentum_block, \
        "MomentumClassify and persistence updates must be inside if(h1_brain.momentum.valid) guard"


def test_source_volatility_persistence_guarded_by_valid():
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    update_func = re.search(r"void\s+UpdateH1Brain\s*\(\s*\)", source)
    assert update_func, "UpdateH1Brain function not found"

    func_start = update_func.start()
    brace_count = 0
    func_end = func_start
    in_func = False
    for i, c in enumerate(source[func_start:], func_start):
        if c == "{":
            brace_count += 1
            in_func = True
        elif c == "}":
            brace_count -= 1
            if brace_count == 0 and in_func:
                func_end = i + 1
                break

    func_body = source[func_start:func_end]

    volatility_block = re.search(
        r"VolatilityEngine\s*\([^)]+\)\s*;\s*"
        r"if\s*\(\s*h1_brain\.volatility\.valid\s*\)\s*\{[^}]*VolatilityLevelClassify",
        func_body, re.DOTALL
    )
    assert volatility_block, \
        "VolatilityLevelClassify and persistence updates must be inside if(h1_brain.volatility.valid) guard"


def test_source_replay_calls_reset_h1_brain_invalid():
    """Replay must call ResetH1BrainInvalid(replayBrain) before B05 engines."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"H1BrainResult\s+replayBrain;\s*\n\s*ResetH1BrainInvalid\(replayBrain\)"
    assert re.search(pattern, source), "Replay must call ResetH1BrainInvalid(replayBrain)"


def test_source_replay_direction_gated_by_valid():
    """Replay DirectionClassify must be inside if(replayBrain.direction.valid)."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"if\s*\(\s*replayBrain\.direction\.valid\s*\)\s*\{[\s\S]*?DirectionClassify"
    assert re.search(pattern, source), "DirectionClassify must be gated by replayBrain.direction.valid"


def test_source_replay_momentum_gated_by_valid():
    """Replay MomentumClassify must be inside if(replayBrain.momentum.valid)."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"if\s*\(\s*replayBrain\.momentum\.valid\s*\)\s*\{[\s\S]*?MomentumClassify"
    assert re.search(pattern, source), "MomentumClassify must be gated by replayBrain.momentum.valid"


def test_source_replay_volatility_gated_by_valid():
    """Replay VolatilityLevelClassify must be inside if(replayBrain.volatility.valid)."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"if\s*\(\s*replayBrain\.volatility\.valid\s*\)\s*\{[\s\S]*?VolatilityLevelClassify"
    assert re.search(pattern, source), "VolatilityLevelClassify must be gated by replayBrain.volatility.valid"


def test_source_replay_no_obsolete_mpersist_reset():
    """Replay must NOT contain the obsolete post-classification high-band mPersist=0 reset."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    # Scope to the replay loop body (after the for-loop start)
    replay_section = source.split("for(int t = warmup; t < copiedRates; t++)")[1]
    assert "if(mState == MOMENTUM_EXPANDING || mState == MOMENTUM_STRONG)" not in replay_section, \
        "Replay must not contain obsolete mState high-band check"
    assert "mPersist = 0;" not in replay_section, \
        "Replay must not contain obsolete mPersist = 0 reset in loop body"


def test_source_replay_quality_gated_by_valid():
    """Replay VolatilityQualityEngine + VolatilityQualitySelect must be inside if(replayBrain.volatility.valid)."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"if\s*\(\s*replayBrain\.volatility\.valid\s*\)\s*\{[\s\S]*?VolatilityQualityEngine"
    assert re.search(pattern, source), \
        "VolatilityQualityEngine must be gated by replayBrain.volatility.valid"
    pattern2 = r"if\s*\(\s*replayBrain\.volatility\.valid\s*\)\s*\{[\s\S]*?VolatilityQualitySelect"
    assert re.search(pattern2, source), \
        "VolatilityQualitySelect must be gated by replayBrain.volatility.valid"


def test_source_live_quality_challenger_globals_exist():
    """Live caller must declare b05_vol_quality_challenger and b05_vol_quality_challenger_dwell."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "b05_vol_quality_challenger" in source, \
        "Live caller must declare b05_vol_quality_challenger"
    assert "b05_vol_quality_challenger_dwell" in source, \
        "Live caller must declare b05_vol_quality_challenger_dwell"


def test_source_volatility_quality_select_has_challenger_params():
    """VolatilityQualitySelect must accept challenger and challengerDwell parameters."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"void\s+VolatilityQualitySelect\s*\([^)]*challenger[^)]*\)"
    assert re.search(pattern, source, re.DOTALL), \
        "VolatilityQualitySelect must accept challenger parameters"


def test_source_volatility_quality_select_no_incumbent_dwell_param():
    """VolatilityQualitySelect must NOT accept incumbentDwell parameter (removed)."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    # Find the function signature
    match = re.search(r"void\s+VolatilityQualitySelect\s*\(([^)]*)\)", source, re.DOTALL)
    assert match, "VolatilityQualitySelect not found"
    params = match.group(1)
    assert "incumbentDwell" not in params, \
        "VolatilityQualitySelect must NOT have incumbentDwell parameter (replaced by challenger dwell)"


def test_source_brain_vol_quality_ready_exists():
    """BrainVolQualityReady helper must exist in MarketBrain.mqh."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "BrainVolQualityReady" in source, \
        "BrainVolQualityReady helper must exist"
    assert "2 * BRAIN_DISPLACEMENT_BARS + 1" in source, \
        "BrainVolQualityReady must use 2 * BRAIN_DISPLACEMENT_BARS + 1"


def test_source_volatility_quality_engine_memory_safe():
    """VolatilityQualityEngine must check BrainVolQualityReady before accessing indices."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    # Find the function
    match = re.search(r"void\s+VolatilityQualityEngine\s*\(", source)
    assert match, "VolatilityQualityEngine not found"
    # Get the function body
    func_start = match.start()
    brace_count = 0
    func_end = func_start
    in_func = False
    for i, c in enumerate(source[func_start:], func_start):
        if c == "{":
            brace_count += 1
            in_func = True
        elif c == "}":
            brace_count -= 1
            if brace_count == 0 and in_func:
                func_end = i + 1
                break
    func_body = source[func_start:func_end]
    assert "BrainVolQualityReady(count)" in func_body, \
        "VolatilityQualityEngine must check BrainVolQualityReady(count)"
    # Must set all quality evidence outputs to defaults
    assert "compressionScore = 0.0" in func_body or "compressionScore=0.0" in func_body, \
        "VolatilityQualityEngine must set compressionScore=0.0 in not-ready path"
    assert "expansionScore = 0.0" in func_body or "expansionScore=0.0" in func_body, \
        "VolatilityQualityEngine must set expansionScore=0.0 in not-ready path"


def test_source_live_quality_gated_by_readiness():
    """Live caller must gate VolatilityQualityEngine + VolatilityQualitySelect behind BrainVolQualityReady."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    # Live section: VolatilityQualityEngine must be inside BrainVolQualityReady gate
    pattern = r"if\s*\(\s*BrainVolQualityReady\s*\(\s*copiedRates\s*\)\s*\)\s*\{[^}]*VolatilityQualityEngine"
    assert re.search(pattern, source, re.DOTALL), \
        "Live VolatilityQualityEngine must be gated by BrainVolQualityReady(copiedRates)"
    pattern2 = r"if\s*\(\s*BrainVolQualityReady\s*\(\s*copiedRates\s*\)\s*\)\s*\{[^}]*VolatilityQualitySelect"
    assert re.search(pattern2, source, re.DOTALL), \
        "Live VolatilityQualitySelect must be gated by BrainVolQualityReady(copiedRates)"


def test_source_replay_quality_gated_by_readiness():
    """Replay caller must gate VolatilityQualityEngine + VolatilityQualitySelect behind BrainVolQualityReady."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    # Replay section: VolatilityQualityEngine must be inside BrainVolQualityReady gate
    pattern = r"if\s*\(\s*BrainVolQualityReady\s*\(\s*count\s*\)\s*\)\s*\{[^}]*VolatilityQualityEngine"
    assert re.search(pattern, source, re.DOTALL), \
        "Replay VolatilityQualityEngine must be gated by BrainVolQualityReady(count)"
    pattern2 = r"if\s*\(\s*BrainVolQualityReady\s*\(\s*count\s*\)\s*\)\s*\{[^}]*VolatilityQualitySelect"
    assert re.search(pattern2, source, re.DOTALL), \
        "Replay VolatilityQualitySelect must be gated by BrainVolQualityReady(count)"
