from __future__ import annotations

import pytest

from nodes.kernel.errors import (
    CollisionError,
    FacetError,
    IdError,
    InvariantError,
    NodesError,
    RefError,
    UnknownKindError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc",
    [IdError, RefError, CollisionError, UnknownKindError, FacetError, InvariantError, ValidationError],
)
def test_all_errors_subclass_base(exc):
    assert issubclass(exc, NodesError)
    assert issubclass(NodesError, Exception)
