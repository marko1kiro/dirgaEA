from reference_momentum import momentum_result, MOMENTUM


def test_adx_unavailable_does_not_invalidate_momentum():
    r = momentum_result(strength=0.7, slope=0.0, adx_available=False)
    assert r["valid"] is True
    assert r["helper_degraded"] == "adx"


def test_invalid_required_input_invalidates():
    r = momentum_result(strength=None, slope=0.0, adx_available=True)
    assert r["valid"] is False
    assert r["state"] == MOMENTUM.NORMAL
    assert r["helper_degraded"] is None


def test_valid_momentum_not_degraded():
    r = momentum_result(strength=0.7, slope=0.0, adx_available=True)
    assert r["valid"] is True
    assert r["helper_degraded"] is None
