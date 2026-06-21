from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.vocab.source import SOURCE, Source, require_identifiable_source, source_of


def _paper(source: dict | None) -> Node:
    facets = {} if source is None else {SOURCE: source}
    return Node(id="paper:x", kind="paper", title="X", facets=facets)


def test_source_defaults():
    s = Source()
    assert s.authors == []
    assert s.year is None and s.container is None and s.identifier is None and s.url is None


def test_source_of_missing_facet_raises():
    with pytest.raises(FacetError):
        source_of(_paper(None))


def test_source_of_unknown_key_raises_facet_error():
    with pytest.raises(FacetError):
        source_of(_paper({"identifer": "10.1/x"}))  # typo: identifer


def test_source_of_wrong_type_raises_facet_error():
    with pytest.raises(FacetError):
        source_of(_paper({"year": "soon"}))


def test_require_identifiable_source_rejects_empty():
    with pytest.raises(InvariantError):
        require_identifiable_source(_paper({}))


def test_require_identifiable_source_accepts_one_field():
    require_identifiable_source(_paper({"year": 2026}))  # no raise


def test_source_roundtrips_through_facets():
    node = _paper({"authors": ["A. Author"], "year": 2026, "identifier": "10.1/x"})
    s = source_of(node)
    assert s.authors == ["A. Author"] and s.year == 2026 and s.identifier == "10.1/x"
