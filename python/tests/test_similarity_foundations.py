from __future__ import annotations

import math

import pytest

from nodes.kernel.node import Node
from nodes.kernel.similarity import (
    _normalize,
    _validate_finite,
    embed_text,
    text_hash,
    validate_namespace,
    validate_text_hash,
)


def test_embed_text_joins_title_and_body_with_blank_line():
    node = Node(id="topic:x", kind="topic", title="Title", body="line one\nline two")
    assert embed_text(node) == "Title\n\nline one\nline two"


def test_text_hash_is_sha256_of_utf8():
    import hashlib

    assert text_hash("café") == hashlib.sha256("café".encode("utf-8")).hexdigest()


@pytest.mark.parametrize("ns", ["model-v1", "openai.text-3", "A_b.C-1"])
def test_validate_namespace_accepts_safe(ns):
    validate_namespace(ns)  # no raise


@pytest.mark.parametrize("ns", ["", ".", "..", "a/b", "a b", "a\0b", "naïve"])
def test_validate_namespace_rejects_unsafe(ns):
    with pytest.raises(ValueError):
        validate_namespace(ns)


@pytest.mark.parametrize("h", ["a" * 64, "0123456789abcdef" * 4])
def test_validate_text_hash_accepts_64_lower_hex(h):
    validate_text_hash(h)  # no raise


@pytest.mark.parametrize(
    "h", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65, "../" + "a" * 61]
)
def test_validate_text_hash_rejects_bad(h):
    with pytest.raises(ValueError):
        validate_text_hash(h)


def test_validate_finite_rejects_empty_and_nonfinite():
    _validate_finite((1.0, 2.0))  # ok
    _validate_finite((1, 2.0))     # ints are accepted and later coerced to float
    with pytest.raises(ValueError):
        _validate_finite(())
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            _validate_finite((1.0, bad))
    for bad in (True, False, "1.0"):
        with pytest.raises(ValueError):
            _validate_finite((1.0, bad))


def test_validate_finite_rejects_out_of_range_int():
    # Out-of-range int (> float max) should raise ValueError, not OverflowError
    with pytest.raises(ValueError):
        _validate_finite((10**309, 1.0))


def test_normalize_unit_length_and_rejects_zero():
    nv = _normalize((3.0, 4.0))
    assert nv == pytest.approx((0.6, 0.8))
    assert math.isclose(math.sqrt(sum(x * x for x in nv)), 1.0)
    with pytest.raises(ValueError):
        _normalize((0.0, 0.0))
