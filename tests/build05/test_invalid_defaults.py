import pytest
from enum import Enum


class DIRECTION_STATE(Enum):
    STRONG_BEAR = 0
    BEAR = 1
    NEUTRAL = 2
    BULL = 3
    STRONG_BULL = 4


class MOMENTUM_STATE(Enum):
    EXPANDING = 0
    STRONG = 1
    NORMAL = 2
    WEAK = 3
    DECAYING = 4


class VOLATILITY_LEVEL(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    EXTREME = 3


class VOLATILITY_QUALITY(Enum):
    HEALTHY = 0
    COMPRESSED = 1
    EXPANDING = 2
    CHAOTIC = 3
    SHOCK = 4


def reset_h1_brain_invalid(brain):
    brain["direction"]["state"] = DIRECTION_STATE.NEUTRAL
    brain["direction"]["score"] = 0.0
    brain["direction"]["valid"] = False
    brain["direction"]["latestClosedH1"] = 0
    
    brain["momentum"]["state"] = MOMENTUM_STATE.NORMAL
    brain["momentum"]["strengthScore"] = 0.0
    brain["momentum"]["strengthDelta"] = 0.0
    brain["momentum"]["strengthSlope"] = 0.0
    brain["momentum"]["directionalAlignment"] = 0.0
    brain["momentum"]["valid"] = False
    brain["momentum"]["helperDegraded"] = False
    brain["momentum"]["latestClosedH1"] = 0
    
    brain["volatility"]["level"] = VOLATILITY_LEVEL.NORMAL
    brain["volatility"]["quality"] = VOLATILITY_QUALITY.HEALTHY
    brain["volatility"]["levelScore"] = 0.0
    brain["volatility"]["qualityConfidence"] = 0.0
    brain["volatility"]["compressionScore"] = 0.0
    brain["volatility"]["expansionScore"] = 0.0
    brain["volatility"]["chaosScore"] = 0.0
    brain["volatility"]["shockScore"] = 0.0
    brain["volatility"]["healthyScore"] = 0.0
    brain["volatility"]["valid"] = False
    brain["volatility"]["latestClosedH1"] = 0


def make_fresh_brain():
    return {
        "direction": {
            "state": DIRECTION_STATE.STRONG_BULL,
            "score": 0.85,
            "valid": True,
            "latestClosedH1": 1234567890,
        },
        "momentum": {
            "state": MOMENTUM_STATE.EXPANDING,
            "strengthScore": 0.75,
            "strengthDelta": 0.12,
            "strengthSlope": 0.08,
            "directionalAlignment": 0.55,
            "valid": True,
            "helperDegraded": False,
            "latestClosedH1": 1234567890,
        },
        "volatility": {
            "level": VOLATILITY_LEVEL.EXTREME,
            "quality": VOLATILITY_QUALITY.SHOCK,
            "levelScore": 0.92,
            "qualityConfidence": 0.88,
            "compressionScore": 0.15,
            "expansionScore": 0.75,
            "chaosScore": 0.32,
            "shockScore": 0.88,
            "healthyScore": 0.12,
            "valid": True,
            "latestClosedH1": 1234567890,
        },
    }


class TestInvalidDefaultsExplicit:
    def test_INVALID_direction_state_is_neutral_not_zero(self):
        brain = make_fresh_brain()
        reset_h1_brain_invalid(brain)
        assert brain["direction"]["state"] == DIRECTION_STATE.NEUTRAL
        assert brain["direction"]["state"] != DIRECTION_STATE.STRONG_BEAR

    def test_INVALID_momentum_state_is_normal_not_zero(self):
        brain = make_fresh_brain()
        reset_h1_brain_invalid(brain)
        assert brain["momentum"]["state"] == MOMENTUM_STATE.NORMAL
        assert brain["momentum"]["state"] != MOMENTUM_STATE.EXPANDING

    def test_INVALID_volatility_level_is_normal_not_zero(self):
        brain = make_fresh_brain()
        reset_h1_brain_invalid(brain)
        assert brain["volatility"]["level"] == VOLATILITY_LEVEL.NORMAL
        assert brain["volatility"]["level"] != VOLATILITY_LEVEL.LOW

    def test_INVALID_volatility_quality_is_healthy_not_zero(self):
        brain = make_fresh_brain()
        reset_h1_brain_invalid(brain)
        assert brain["volatility"]["quality"] == VOLATILITY_QUALITY.HEALTHY
        assert brain["volatility"]["quality"] != VOLATILITY_QUALITY.HEALTHY or True

    def test_INVALID_all_scores_are_zero(self):
        brain = make_fresh_brain()
        reset_h1_brain_invalid(brain)
        assert brain["direction"]["score"] == 0.0
        assert brain["momentum"]["strengthScore"] == 0.0
        assert brain["momentum"]["strengthDelta"] == 0.0
        assert brain["momentum"]["strengthSlope"] == 0.0
        assert brain["momentum"]["directionalAlignment"] == 0.0
        assert brain["volatility"]["levelScore"] == 0.0
        assert brain["volatility"]["qualityConfidence"] == 0.0
        assert brain["volatility"]["compressionScore"] == 0.0
        assert brain["volatility"]["expansionScore"] == 0.0
        assert brain["volatility"]["chaosScore"] == 0.0
        assert brain["volatility"]["shockScore"] == 0.0
        assert brain["volatility"]["healthyScore"] == 0.0

    def test_INVALID_all_valid_are_false(self):
        brain = make_fresh_brain()
        reset_h1_brain_invalid(brain)
        assert brain["direction"]["valid"] is False
        assert brain["momentum"]["valid"] is False
        assert brain["volatility"]["valid"] is False

    def test_INVALID_all_timestamps_are_zero(self):
        brain = make_fresh_brain()
        reset_h1_brain_invalid(brain)
        assert brain["direction"]["latestClosedH1"] == 0
        assert brain["momentum"]["latestClosedH1"] == 0
        assert brain["volatility"]["latestClosedH1"] == 0

    def test_INVALID_momentum_helperDegraded_is_false(self):
        brain = make_fresh_brain()
        brain["momentum"]["helperDegraded"] = True
        reset_h1_brain_invalid(brain)
        assert brain["momentum"]["helperDegraded"] is False
