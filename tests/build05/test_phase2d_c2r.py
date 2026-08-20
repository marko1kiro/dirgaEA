import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parents[2]
PRODUCTION = sorted((*BASE.glob("*.mq5"), *BASE.glob("*.mqh")))
MQ5 = BASE / "AdaptiveSurvivalEA.mq5"
BRAIN = BASE / "MarketBrain.mqh"
DIAGNOSTICS = BASE / "DiagnosticCollector.mqh"


def _masked(source):
    out = list(source)
    i = 0
    state = "code"
    quote = ""
    while i < len(source):
        if state == "code":
            if source.startswith("//", i):
                out[i:i + 2] = "  "
                i += 2
                state = "line"
            elif source.startswith("/*", i):
                out[i:i + 2] = "  "
                i += 2
                state = "block"
            elif source[i] in "\"'":
                quote = source[i]
                out[i] = " "
                i += 1
                state = "string"
            else:
                i += 1
        elif state == "line":
            if source[i] == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
        elif state == "block":
            if source.startswith("*/", i):
                out[i:i + 2] = "  "
                i += 2
                state = "code"
            else:
                if source[i] != "\n":
                    out[i] = " "
                i += 1
        else:
            if source[i] == "\\" and i + 1 < len(source):
                out[i:i + 2] = "  "
                i += 2
            elif source[i] == quote:
                out[i] = " "
                i += 1
                state = "code"
            else:
                if source[i] != "\n":
                    out[i] = " "
                i += 1
    return "".join(out)


def _balanced(source, opening):
    masked = _masked(source)
    pairs = {"(": ")", "{": "}", "[": "]"}
    stack = []
    for i in range(opening, len(masked)):
        c = masked[i]
        if c in pairs:
            stack.append(pairs[c])
        elif c in ")}]":
            assert stack and c == stack.pop()
            if not stack:
                return source[opening:i + 1], masked[opening:i + 1]
    raise AssertionError("unbalanced source")


def _function(source, name):
    masked = _masked(source)
    match = re.search(r"\b" + re.escape(name) + r"\s*\(", masked)
    assert match, f"{name} not found"
    opening = masked.find("{", match.end())
    assert opening >= 0, f"{name} body not found"
    return _balanced(source, opening)[0]


def _calls(source, name):
    masked = _masked(source)
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", masked):
        opening = masked.find("(", match.start())
        yield _balanced(source, opening)


def _top_level_argument_count(masked_call):
    depth = 0
    commas = 0
    content = False
    for c in masked_call[1:-1]:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            commas += 1
        elif not c.isspace():
            content = True
    return commas + 1 if content else 0


def _diagnostic_adx_model(adx_buffer_ready, copied_adx):
    indices = []
    current = previous = slope = 0.0
    if adx_buffer_ready and copied_adx >= 2:
        indices = [copied_adx - 1, copied_adx - 2]
        current, previous = 2.0, 1.0
        slope = current - previous
    return current, previous, slope, indices


def test_canonical_uses_only_real_behavior_members_and_has_no_logging():
    body = _function(BRAIN.read_text(encoding="utf-8"), "ProcessBuild05ClosedHistoryPrefix")
    masked = _masked(body)
    invalid = ["direction", "momentum", "volQualityBucket", "lastAcceptedH1"]
    for member in invalid:
        assert not re.search(r"\bstate\s*\.\s*" + member + r"\b", masked), member
    assert not list(_calls(body, "LogDebug"))


def test_all_production_logdebug_calls_have_two_top_level_arguments():
    failures = []
    for path in PRODUCTION:
        for raw, masked in _calls(path.read_text(encoding="utf-8"), "LogDebug"):
            count = _top_level_argument_count(masked)
            if count != 2:
                failures.append((path.name, count, raw.splitlines()[0]))
    assert failures == []


def test_adx_diagnostics_are_guarded_before_indexing():
    body = _function(MQ5.read_text(encoding="utf-8"), "UpdateH1Brain")
    masked = _masked(body)
    guard = re.search(r"if\s*\(\s*adxBufferReady\s*&&\s*copiedAdx\s*>=\s*2\s*\)\s*\{", masked)
    assert guard, "missing adxBufferReady && copiedAdx >= 2 guard"
    opening = body.find("{", guard.start())
    guarded_body = _balanced(body, opening)[1]
    outside = masked[:opening] + " " * len(guarded_body) + masked[opening + len(guarded_body):]
    assert not re.search(r"\badx\s*\[\s*[^\]\s]", outside), "ADX indexed outside proven guard"


def test_adx_diagnostic_edge_model_never_indexes_short_buffers():
    for copied in (-1, 0, 1):
        assert _diagnostic_adx_model(True, copied) == (0.0, 0.0, 0.0, [])
    assert _diagnostic_adx_model(False, 2) == (0.0, 0.0, 0.0, [])


def test_b05d2_signature_locks_ascii_fnv1a_and_required_fields():
    body = _function(DIAGNOSTICS.read_text(encoding="utf-8"), "Build05DiagnosticSignature")
    masked = _masked(body)
    required = (
        "s.directionState", "s.momentumState", "s.volLevel", "s.volQuality",
        "s.directionDwell", "s.directionChallenger", "s.directionChallengerDwell",
        "s.momentumPersist", "s.prevMomentumStrength", "s.momentumStrengthPrimed",
        "s.volLevelDwell", "s.volLevelChallenger", "s.volLevelChallengerDwell",
        "s.volQualityPrimed", "s.volQualityChallenger", "s.volQualityChallengerDwell",
        "s.volQualityReady",
    )
    for token in required:
        assert token in masked, token
    assert re.search(r"Build04DiagnosticAscii\s*\(\s*out\s*\)", masked)
    assert re.search(r"ulong\s+hash\s*=\s*14695981039346656037\s*;", masked)
    assert re.search(r"hash\s*\^=\s*\(\s*ulong\s*\)\s*byteValue\s*;", masked)
    assert re.search(r"hash\s*\*=\s*1099511628211\s*;", masked)
    assert "CalculateSHA256" not in masked
