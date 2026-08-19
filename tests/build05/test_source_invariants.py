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
