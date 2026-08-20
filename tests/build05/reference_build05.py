import dataclasses
import math

from reference_direction import DIRECTION, direction_enum
from reference_momentum import MOMENTUM, momentum_engine_direction_agnostic, momentum_enum
from reference_volatility import VOL_LEVEL, VOL_QUALITY, compute_quality_evidence, quality_enum, volatility_level_enum


@dataclasses.dataclass
class BehaviorState:
    directionState: DIRECTION = DIRECTION.NEUTRAL
    directionDwell: int = 0
    directionChallenger: DIRECTION = DIRECTION.NEUTRAL
    directionChallengerDwell: int = 0
    momentumState: MOMENTUM = MOMENTUM.NORMAL
    momentumPersist: int = 0
    prevMomentumStrength: float = 0.0
    momentumStrengthPrimed: bool = False
    volLevel: VOL_LEVEL = VOL_LEVEL.NORMAL
    volLevelDwell: int = 0
    volLevelChallenger: VOL_LEVEL = VOL_LEVEL.NORMAL
    volLevelChallengerDwell: int = 0
    volQuality: VOL_QUALITY = VOL_QUALITY.HEALTHY
    volQualityConfidence: float = 0.0
    volQualityPrimed: bool = False
    volQualityChallenger: VOL_QUALITY = VOL_QUALITY.HEALTHY
    volQualityChallengerDwell: int = 0
    volQualityReady: bool = False


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _tanh(v):
    return math.tanh(v)


def _direction(rates, atr, fast, slow):
    n = len(rates) - 1
    a = atr[n]
    displacement = (rates[n]["close"] - rates[n - 20]["close"]) / a if n >= 20 else 0.0
    closes = [x["close"] for x in rates]
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - 20, len(closes))) if n >= 20 else 0.0
    efficiency = (closes[-1] - closes[-21]) / path if path else 0.0
    positioning = (0.5 if rates[n]["close"] > fast[n] else -0.5) + (0.5 if rates[n]["close"] > slow[n] else -0.5)
    raw = 0.30 * _tanh((fast[n] - fast[n - 2]) / a) + 0.25 * _tanh((slow[n] - slow[n - 2]) / a) + 0.15 * _clamp(positioning, -1, 1) + 0.15 * _tanh(displacement) + 0.15 * _clamp(efficiency, -1, 1)
    return _clamp(raw, -1, 1)


def process_prefix(rates, atr, fast, slow, adx, state):
    score = _direction(rates, atr, fast, slow)
    ds = direction_enum(score, state.directionState, state.directionDwell, state.directionChallenger, state.directionChallengerDwell)
    state.directionState, state.directionDwell, state.directionChallenger, state.directionChallengerDwell = ds
    momentum = momentum_engine_direction_agnostic(rates, atr[-1])
    strength = momentum["strength"]
    delta = strength - state.prevMomentumStrength if state.momentumStrengthPrimed else 0.0
    slope = _clamp(delta, -1, 1)
    persist = [state.momentumPersist]
    state.momentumState = momentum_enum(strength, slope, state.momentumState, persist)
    state.momentumPersist = persist[0]
    state.prevMomentumStrength = strength
    state.momentumStrengthPrimed = True
    baseline = sum(atr[-min(50, len(atr)):]) / min(50, len(atr))
    ratio = atr[-1] / baseline
    vl = volatility_level_enum(ratio, state.volLevel, state.volLevelDwell, state.volLevelChallenger, state.volLevelChallengerDwell)
    state.volLevel, state.volLevelDwell, state.volLevelChallenger, state.volLevelChallengerDwell = vl
    state.volQualityReady = len(rates) >= 41
    evidence = compute_quality_evidence(rates, atr)
    if state.volQualityReady:
        q = quality_enum(evidence, state.volQuality, state.volQualityPrimed, state.volQualityChallenger, state.volQualityChallengerDwell)
        state.volQuality, state.volQualityConfidence, state.volQualityPrimed, state.volQualityChallenger, state.volQualityChallengerDwell = q
    result = {"closed_h1": rates[-1]["time"], "direction": (state.directionState, score, True), "momentum": (state.momentumState, strength, delta, slope, momentum["directionalAlignment"], True, False), "volatility": (state.volLevel, state.volQuality, _clamp(ratio / 2.0, 0, 1), state.volQualityConfidence, evidence, True)}
    return result


def _decimal(value):
    text = f"{value:.15f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _enum(value, offset=0):
    return value.value + offset


def canonical_ascii(result, state):
    direction = result["direction"]
    momentum = result["momentum"]
    volatility = result["volatility"]
    evidence = volatility[4]
    closed_h1 = result["closed_h1"]
    fields = [
        ("dstate", _enum(direction[0], 2)), ("dscore", _decimal(direction[1])), ("dvalid", int(direction[2])), ("dtime", closed_h1),
        ("ddwell", state.directionDwell), ("dch", _enum(state.directionChallenger, 2)), ("dchd", state.directionChallengerDwell),
        ("mstate", _enum(momentum[0])), ("mstrength", _decimal(momentum[1])), ("mdelta", _decimal(momentum[2])), ("mslope", _decimal(momentum[3])), ("malign", _decimal(momentum[4])), ("mvalid", int(momentum[5])), ("mdegraded", int(momentum[6])), ("mtime", closed_h1),
        ("mpersist", state.momentumPersist), ("mpstr", _decimal(state.prevMomentumStrength)), ("mprmd", int(state.momentumStrengthPrimed)),
        ("vlevel", _enum(volatility[0])), ("vlscore", _decimal(volatility[2])), ("vvalid", int(volatility[5])), ("vtime", closed_h1),
        ("vldwell", state.volLevelDwell), ("vlch", _enum(state.volLevelChallenger)), ("vlchd", state.volLevelChallengerDwell),
        ("vquality", _enum(volatility[1])), ("vqconf", _decimal(volatility[3])), ("vqcomp", _decimal(evidence["compression"])), ("vqexp", _decimal(evidence["expansion"])), ("vqchaos", _decimal(evidence["chaos"])), ("vqshock", _decimal(evidence["shock"])), ("vqhealth", _decimal(evidence["healthy"])),
        ("vqprmd", int(state.volQualityPrimed)), ("vqch", _enum(state.volQualityChallenger)), ("vqchd", state.volQualityChallengerDwell),
        ("dstate_h", _enum(state.directionState, 2)), ("mstate_h", _enum(state.momentumState)), ("vlstate_h", _enum(state.volLevel)), ("vqstate_h", _enum(state.volQuality)), ("vqready", int(state.volQualityReady)),
    ]
    return "v=B05D2;" + "".join(f"{key}={value};" for key, value in fields)


def fnv1a64(data):
    value = 14695981039346656037
    for byte in data:
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def signature(result, state):
    canonical = canonical_ascii(result, state)
    return f"B05D2:{fnv1a64(canonical.encode('ascii')):X}"


def count_copy_failures(expected, *copied):
    return sum(value != expected for value in copied)


def fixture(count=47):
    rates = []
    atr = []
    close = 100.0
    for i in range(count):
        move = 1.3 if i < 28 else (-0.8 if i % 3 else 1.7)
        close += move
        body = 1.2 if i < 30 else 0.45 + (i % 4) * 0.2
        open_ = close - (body if move >= 0 else -body)
        rates.append({"time": 1700000000 + i * 3600, "open": open_, "high": max(open_, close) + 0.3, "low": min(open_, close) - 0.4, "close": close})
        atr.append(1.0 if i < 25 else 1.0 + (i - 24) * 0.08)
    fast = [r["close"] - 0.4 for r in rates]
    slow = [r["close"] - 1.0 for r in rates]
    adx = [20.0 + i * 0.1 for i in range(count)]
    return rates, atr, fast, slow, adx
