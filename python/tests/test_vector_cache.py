from __future__ import annotations

import json

import pytest

from nodes.kernel.similarity import VectorCache

H = "a" * 64   # a valid 64-char lowercase-hex cache key
H2 = "b" * 64


def test_put_then_get_roundtrips_raw_vector(tmp_path):
    cache = VectorCache(tmp_path)
    cache.put("model-v1", H, (0.5, -0.25, 2.0))
    assert cache.get("model-v1", H) == (0.5, -0.25, 2.0)


def test_get_miss_returns_none(tmp_path):
    assert VectorCache(tmp_path).get("model-v1", H2) is None


def test_namespaces_are_isolated(tmp_path):
    cache = VectorCache(tmp_path)
    cache.put("model-a", H, (1.0,))
    assert cache.get("model-b", H) is None


def test_put_writes_expected_json_with_dim(tmp_path):
    cache = VectorCache(tmp_path)
    cache.put("model-v1", H, (1.0, 2.0))
    path = tmp_path / ".nodes-index" / "vectors" / "model-v1" / f"{H}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"dim": 2, "vector": [1.0, 2.0]}


def test_invalid_namespace_rejected(tmp_path):
    with pytest.raises(ValueError):
        VectorCache(tmp_path).get("../escape", H)


def test_path_traversal_key_rejected(tmp_path):
    cache = VectorCache(tmp_path)
    with pytest.raises(ValueError):
        cache.get("model-v1", "../../etc/passwd")
    with pytest.raises(ValueError):
        cache.put("model-v1", "..", (1.0,))


def test_non_hex_or_wrong_length_key_rejected(tmp_path):
    with pytest.raises(ValueError):
        VectorCache(tmp_path).get("model-v1", "not-a-hash")
    with pytest.raises(ValueError):
        VectorCache(tmp_path).get("model-v1", "A" * 64)  # uppercase not allowed


def test_corrupt_file_fails_early(tmp_path):
    cache = VectorCache(tmp_path)
    path = tmp_path / ".nodes-index" / "vectors" / "model-v1" / f"{H}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        cache.get("model-v1", H)


def test_dim_length_mismatch_fails_early(tmp_path):
    cache = VectorCache(tmp_path)
    path = tmp_path / ".nodes-index" / "vectors" / "model-v1" / f"{H}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"dim": 3, "vector": [1.0, 2.0]}), encoding="utf-8")
    with pytest.raises(ValueError):
        cache.get("model-v1", H)


def test_bool_vector_element_in_cache_fails_early(tmp_path):
    cache = VectorCache(tmp_path)
    path = tmp_path / ".nodes-index" / "vectors" / "model-v1" / f"{H}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"dim": 1, "vector": [True]}), encoding="utf-8")
    with pytest.raises(ValueError):
        cache.get("model-v1", H)


def test_put_rejects_nonfinite(tmp_path):
    with pytest.raises(ValueError):
        VectorCache(tmp_path).put("model-v1", H, (float("nan"),))


def test_put_rejects_bool(tmp_path):
    with pytest.raises(ValueError):
        VectorCache(tmp_path).put("model-v1", H, (True,))
