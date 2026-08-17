from reference_momentum import momentum_enum, MOMENTUM


def _seq(strengths, slopes):
    out = []
    for st, sl in zip(strengths, slopes):
        prev = out[-1] if out else MOMENTUM.NORMAL
        out.append(momentum_enum(st, sl, prev=prev))
    return out


def test_expanding_vs_strong_uses_slope():
    # same strength, rising slope => EXPANDING; flat/falling => STRONG
    a = _seq([0.8, 0.8], [0.3, 0.0])
    assert a[0] == MOMENTUM.EXPANDING and a[1] == MOMENTUM.STRONG


def test_weak_vs_decaying_uses_slope():
    b = _seq([0.3, 0.3], [0.0, -0.3])
    assert b[0] == MOMENTUM.WEAK and b[1] == MOMENTUM.DECAYING


def test_state_persistence_no_flip_on_single_bar():
    c = _seq([0.8, 0.2, 0.2, 0.8, 0.2, 0.8, 0.2, 0.8], [0.0] * 8)
    # EXPANDING/STRONG should not thrash to DECAYING on isolated dips
    assert c.count(MOMENTUM.DECAYING) <= 2


def test_normal_band():
    d = _seq([0.5, 0.5], [0.0, 0.0])
    assert d == [MOMENTUM.NORMAL, MOMENTUM.NORMAL]
