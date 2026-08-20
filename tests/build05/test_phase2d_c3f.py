import copy
import dataclasses
import pathlib
import re

import pytest

from reference_build05 import BehaviorState, fixture, process_prefix, signature

BASE = pathlib.Path(__file__).resolve().parents[2]
EA = BASE / "AdaptiveSurvivalEA.mq5"
DIAG = BASE / "DiagnosticCollector.mqh"


def function(source, name):
    match = re.search(rf"\b(?:void|string)\s+{name}\s*\(", source)
    assert match
    start = source.find("{", match.end())
    depth = 0
    for pos in range(start, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError("unbalanced function")


def non_default_snapshot():
    data = fixture(48)
    state = BehaviorState()
    result = None
    for count in range(41, 48):
        result = process_prefix(*(values[:count] for values in data), state)
    return data, state, result, signature(result, state)


def guarded_attempt(kind, state, result, digest, counters, canonical):
    if kind == "forming":
        counters["forming"] += 1
        return state, result, digest
    if kind == "duplicate":
        counters["duplicate"] += 1
        return state, result, digest
    return canonical()


@pytest.mark.parametrize("kind,counter", [("forming", "forming"), ("duplicate", "duplicate")])
def test_guard_model_preserves_complete_non_default_snapshot_without_canonical(kind, counter):
    _, state, result, digest = non_default_snapshot()
    before = copy.deepcopy((state, result, digest))
    counters = {"forming": 4, "duplicate": 7}
    calls = []
    after = guarded_attempt(kind, state, result, digest, counters, lambda: calls.append(True))
    assert after == before
    assert dataclasses.asdict(after[0]) == dataclasses.asdict(before[0])
    assert counters[counter] == ({"forming": 4, "duplicate": 7}[counter] + 1)
    other = "duplicate" if counter == "forming" else "forming"
    assert counters[other] == {"forming": 4, "duplicate": 7}[other]
    assert calls == []


def test_live_guards_precede_reset_copybuffer_and_canonical():
    body = function(EA.read_text(encoding="utf-8"), "UpdateH1Brain")
    short = body.index("if(copiedRates < 3)")
    resets = [match.start() for match in re.finditer(r"ResetH1BrainInvalid\(h1_brain\)", body)]
    forming = body.index("formingBarAttempts++")
    duplicate = body.index("duplicateH1Attempts++")
    copybuffer = body.index("CopyBrainBuffer(")
    canonical = body.index("ProcessBuild05ClosedHistoryPrefix(")
    assert short < resets[0]
    assert forming < resets[1] < copybuffer
    assert duplicate < resets[1] < canonical


def test_short_history_remains_fail_closed():
    body = function(EA.read_text(encoding="utf-8"), "UpdateH1Brain")
    branch = re.search(r"if\(copiedRates < 3\)\s*\{(.*?)\n\s*\}", body, re.S).group(1)
    assert "ResetH1BrainInvalid(h1_brain)" in branch


def test_compact_runtime_formatter_is_real_code_and_keeps_b05d2_precision():
    source = DIAG.read_text(encoding="utf-8")
    formatter = function(source, "Build05RuntimeMessage")
    serializer = function(source, "Build05RuntimeDecimal")
    assert '"schema=B05T1 h=%I64d d=[%s] m=[%s] v=[%s] p=[%s] sig=%s end=1"' in formatter
    assert "DoubleToString(value, 6)" in serializer
    assert "DoubleToString(value,15)" in function(source, "Build05DiagnosticDecimal")
    collect = function(source, "Build05DiagnosticCollect")
    assert collect.count('LogDebug("BRAIN_UPDATE"') == 1
