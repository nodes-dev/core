from __future__ import annotations

from nodes.kernel.ranking import score_key


def test_score_key_rounds_to_6dp():
    assert score_key(1.2345674) == 1.234567   # rounds down
    assert score_key(1.2345678) == 1.234568   # rounds up
    assert score_key(0.0) == 0.0


def test_score_key_handles_negative():
    # cosine can be negative; floor-based half-up must still round correctly
    assert score_key(-0.3408105) == -0.340810
    assert score_key(-1.0) == -1.0
