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

    early_return_match = re.search(r"if\s*\(\s*copiedRates\s*<\s*3\s*\)\s*(?:return|\{[^{}]*return\s*;[^{}]*\})", func_body, re.DOTALL)
    assert early_return_match, "CopyRates early return check not found"

    assert reset_call_match.start() < early_return_match.start(), \
        "ResetH1BrainInvalid must be called BEFORE CopyRates early return check"


def test_source_direction_persistence_guarded_by_valid():
    """DirectionClassify must be inside if(result.direction.valid) in ProcessBuild05ClosedHistoryPrefix."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(", source)
    assert match, "ProcessBuild05ClosedHistoryPrefix not found"
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

    direction_block = re.search(
        r"DirectionEngine\s*\([^)]+\)\s*;\s*"
        r"if\s*\(\s*result\.direction\.valid\s*\)\s*\{[^}]*DirectionClassify",
        func_body, re.DOTALL
    )
    assert direction_block, \
        "DirectionClassify must be inside if(result.direction.valid) guard in ProcessBuild05ClosedHistoryPrefix"


def test_source_momentum_persistence_guarded_by_valid():
    """MomentumClassify must be inside if(result.momentum.valid) in ProcessBuild05ClosedHistoryPrefix."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(", source)
    assert match, "ProcessBuild05ClosedHistoryPrefix not found"
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

    momentum_block = re.search(
        r"MomentumEngine\s*\([^)]+\)\s*;\s*"
        r"if\s*\(\s*result\.momentum\.valid\s*\)\s*\{[^}]*MomentumClassify",
        func_body, re.DOTALL
    )
    assert momentum_block, \
        "MomentumClassify must be inside if(result.momentum.valid) guard in ProcessBuild05ClosedHistoryPrefix"


def test_source_volatility_persistence_guarded_by_valid():
    """VolatilityLevelClassify must be inside if(result.volatility.valid) in ProcessBuild05ClosedHistoryPrefix."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(", source)
    assert match, "ProcessBuild05ClosedHistoryPrefix not found"
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

    volatility_block = re.search(
        r"VolatilityEngine\s*\([^)]+\)\s*;\s*"
        r"if\s*\(\s*result\.volatility\.valid\s*\)\s*\{[^}]*VolatilityLevelClassify",
        func_body, re.DOTALL
    )
    assert volatility_block, \
        "VolatilityLevelClassify must be inside if(result.volatility.valid) guard in ProcessBuild05ClosedHistoryPrefix"


def test_source_replay_calls_reset_h1_brain_invalid():
    """Replay must call ResetH1BrainInvalid(replayBrain) before B05 engines."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"H1BrainResult\s+replayBrain;\s*\n\s*ResetH1BrainInvalid\(replayBrain\)"
    assert re.search(pattern, source), "Replay must call ResetH1BrainInvalid(replayBrain)"


def test_source_replay_direction_gated_by_valid():
    """Replay uses ProcessBuild05ClosedHistoryPrefix which gates DirectionClassify by valid."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"ProcessBuild05ClosedHistoryPrefix\s*\([^)]*replayB05State[^)]*replayBrain"
    assert re.search(pattern, source), \
        "Replay must call ProcessBuild05ClosedHistoryPrefix with replayB05State and replayBrain"


def test_source_replay_momentum_gated_by_valid():
    """Replay uses ProcessBuild05ClosedHistoryPrefix which gates MomentumClassify by valid."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"ProcessBuild05ClosedHistoryPrefix\s*\([^)]*replayB05State[^)]*replayBrain"
    assert re.search(pattern, source), \
        "Replay must call ProcessBuild05ClosedHistoryPrefix with replayB05State and replayBrain"


def test_source_replay_volatility_gated_by_valid():
    """Replay uses ProcessBuild05ClosedHistoryPrefix which gates VolatilityLevelClassify by valid."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"ProcessBuild05ClosedHistoryPrefix\s*\([^)]*replayB05State[^)]*replayBrain"
    assert re.search(pattern, source), \
        "Replay must call ProcessBuild05ClosedHistoryPrefix with replayB05State and replayBrain"


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
    """Replay uses ProcessBuild05ClosedHistoryPrefix which gates VolatilityQualityEngine by volatility.valid."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"ProcessBuild05ClosedHistoryPrefix\s*\([^)]*replayB05State[^)]*replayBrain"
    assert re.search(pattern, source), \
        "Replay must call ProcessBuild05ClosedHistoryPrefix with replayB05State and replayBrain"
    # Quality engine gating is inside ProcessBuild05ClosedHistoryPrefix (MarketBrain.mqh)


def test_source_live_quality_challenger_globals_exist():
    """Build05BehaviorState must contain volQualityChallenger and volQualityChallengerDwell fields."""
    source_path = os.path.join(SOURCE_DIR, "Types.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"struct Build05BehaviorState\s*\{([^}]+)\}", source, re.DOTALL)
    assert match, "Build05BehaviorState struct not found"
    body = match.group(1)
    assert "volQualityChallenger" in body, \
        "Build05BehaviorState must contain volQualityChallenger field"
    assert "volQualityChallengerDwell" in body, \
        "Build05BehaviorState must contain volQualityChallengerDwell field"


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
    """ProcessBuild05ClosedHistoryPrefix gates VolatilityQualityEngine behind BrainVolQualityReady."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(", source)
    assert match, "ProcessBuild05ClosedHistoryPrefix not found"
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
        "ProcessBuild05ClosedHistoryPrefix must gate VolatilityQualityEngine behind BrainVolQualityReady(count)"
    assert "VolatilityQualityEngine" in func_body, \
        "ProcessBuild05ClosedHistoryPrefix must call VolatilityQualityEngine"


def test_source_replay_quality_gated_by_readiness():
    """Replay uses ProcessBuild05ClosedHistoryPrefix which gates VolQualityEngine behind BrainVolQualityReady."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    pattern = r"ProcessBuild05ClosedHistoryPrefix\s*\([^)]*replayB05State[^)]*replayBrain"
    assert re.search(pattern, source), \
        "Replay must call ProcessBuild05ClosedHistoryPrefix with replayB05State and replayBrain"
    # Readiness gate is inside ProcessBuild05ClosedHistoryPrefix (MarketBrain.mqh) — tested by test_source_live_quality_gated_by_readiness


# ===========================================================================
# PHASE 2D-C INVARINTS — Canonical Behavior State + B05D2 + Diagnostic Closure
# ===========================================================================

def test_source_canonical_function_exists():
    """ProcessBuild05ClosedHistoryPrefix must exist in MarketBrain.mqh."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(", source), \
        "ProcessBuild05ClosedHistoryPrefix function not found"


def test_source_canonical_accepts_behavior_state():
    """ProcessBuild05ClosedHistoryPrefix must accept Build05BehaviorState parameter."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(([^)]*)\)", source, re.DOTALL)
    assert match, "ProcessBuild05ClosedHistoryPrefix not found"
    params = match.group(1)
    assert "Build05BehaviorState" in params, \
        "ProcessBuild05ClosedHistoryPrefix must accept Build05BehaviorState parameter"


def test_source_canonical_accepts_h1_brain_result():
    """ProcessBuild05ClosedHistoryPrefix must accept H1BrainResult parameter."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(([^)]*)\)", source, re.DOTALL)
    assert match, "ProcessBuild05ClosedHistoryPrefix not found"
    params = match.group(1)
    assert "H1BrainResult" in params, \
        "ProcessBuild05ClosedHistoryPrefix must accept H1BrainResult parameter"


def test_source_canonical_fail_closed_resets_brain():
    """ProcessBuild05ClosedHistoryPrefix must call ResetH1BrainInvalid at entry."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(", source)
    assert match, "ProcessBuild05ClosedHistoryPrefix not found"
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
    reset_match = re.search(r"ResetH1BrainInvalid\s*\(\s*result\s*\)", func_body)
    assert reset_match, "ProcessBuild05ClosedHistoryPrefix must call ResetH1BrainInvalid(result) at entry"
    body_len = func_end - func_start
    assert reset_match.start() < body_len * 0.15, \
        "ResetH1BrainInvalid must be called at the beginning of ProcessBuild05ClosedHistoryPrefix"


def test_source_live_uses_canonical_function():
    """UpdateH1Brain must delegate to ProcessBuild05ClosedHistoryPrefix."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    update_match = re.search(r"void\s+UpdateH1Brain\s*\(\s*\)", source)
    assert update_match, "UpdateH1Brain not found"
    func_start = update_match.start()
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
    assert "ProcessBuild05ClosedHistoryPrefix" in func_body, \
        "UpdateH1Brain must call ProcessBuild05ClosedHistoryPrefix"
    assert "b05_state" in func_body, \
        "UpdateH1Brain must pass b05_state to ProcessBuild05ClosedHistoryPrefix"
    assert "h1_brain" in func_body, \
        "UpdateH1Brain must pass h1_brain to ProcessBuild05ClosedHistoryPrefix"


def test_source_live_no_direct_persistence_logic():
    """UpdateH1Brain must NOT contain direct Direction/Momentum/Volatility persistence logic."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    update_match = re.search(r"void\s+UpdateH1Brain\s*\(\s*\)", source)
    assert update_match, "UpdateH1Brain not found"
    func_start = update_match.start()
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
    assert "DirectionClassify" not in func_body, \
        "UpdateH1Brain must not contain direct DirectionClassify (use canonical function)"
    assert "MomentumClassify" not in func_body, \
        "UpdateH1Brain must not contain direct MomentumClassify (use canonical function)"
    assert "VolatilityLevelClassify" not in func_body, \
        "UpdateH1Brain must not contain direct VolatilityLevelClassify (use canonical function)"


def test_source_replay_uses_canonical_function():
    """RebuildRegimeFusionState must use ProcessBuild05ClosedHistoryPrefix with replay-local state."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    rebuild_match = re.search(r"void\s+RebuildRegimeFusionState\s*\(\s*\)", source)
    assert rebuild_match, "RebuildRegimeFusionState not found"
    func_start = rebuild_match.start()
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
    assert "Build05BehaviorState replayB05State" in func_body or "Build05BehaviorState replayB05State;" in func_body, \
        "RebuildRegimeFusionState must declare local Build05BehaviorState replayB05State"
    assert "Build05BehaviorStateInit(replayB05State)" in func_body, \
        "RebuildRegimeFusionState must call Build05BehaviorStateInit(replayB05State)"
    assert "ProcessBuild05ClosedHistoryPrefix" in func_body, \
        "RebuildRegimeFusionState must call ProcessBuild05ClosedHistoryPrefix"


def test_source_replay_hydrates_b05_state():
    """Replay must hydrate b05_state from replayB05State after the replay loop."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    rebuild_match = re.search(r"void\s+RebuildRegimeFusionState\s*\(\s*\)", source)
    assert rebuild_match, "RebuildRegimeFusionState not found"
    func_start = rebuild_match.start()
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
    assert "b05_state = replayB05State" in func_body or "b05_state=replayB05State" in func_body, \
        "Replay must hydrate b05_state = replayB05State after loop"
    assert "h1_brain = replayBrain" in func_body or "h1_brain=replayBrain" in func_body, \
        "Replay must hydrate h1_brain = replayBrain after loop"


def test_source_single_b05_state_global():
    """EA must have exactly one b05_state global — no ad-hoc B05 persistence globals."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "Build05BehaviorState b05_state" in source, \
        "b05_state global declaration not found"
    assert "b05_direction_state" not in source, \
        "Old ad-hoc b05_direction_state must be removed"
    assert "b05_momentum_state" not in source, \
        "Old ad-hoc b05_momentum_state must be removed"
    assert "b05_vol_level " not in source or "b05_vol_level_challenger" in source, \
        "Old ad-hoc b05_vol_level must be removed"


def test_source_build05_behavior_state_struct_exists():
    """Types.mqh must define Build05BehaviorState struct with required fields."""
    source_path = os.path.join(SOURCE_DIR, "Types.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"struct Build05BehaviorState\s*\{([^}]+)\}", source, re.DOTALL)
    assert match, "Build05BehaviorState struct not found"
    body = match.group(1)
    required_fields = [
        "directionState", "directionDwell", "directionChallenger", "directionChallengerDwell",
        "momentumState", "momentumPersist", "prevMomentumStrength", "momentumStrengthPrimed",
        "volLevel", "volLevelDwell", "volLevelChallenger", "volLevelChallengerDwell",
        "volQuality", "volQualityConfidence", "volQualityPrimed",
        "volQualityChallenger", "volQualityChallengerDwell",
    ]
    for field in required_fields:
        assert field in body, f"Build05BehaviorState missing field: {field}"


def test_source_build05_behavior_state_init_exists():
    """MarketBrain.mqh must define Build05BehaviorStateInit."""
    source_path = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "Build05BehaviorStateInit" in source, "Build05BehaviorStateInit not found"
