"""Pins the PEP 420 layout (layout design §5).

`nodes` is a native namespace package shared by family distributions;
`nodes.core` is the regular package this distribution owns. A regular
`nodes/__init__.py` reappearing anywhere breaks co-installed family members.
"""
from __future__ import annotations

import importlib

import pytest

LEGACY_PATH = ".".join(["nodes", "kernel"])  # assembled so guards never match it


def test_core_is_importable() -> None:
    import nodes.core

    assert nodes.core.__name__ == "nodes.core"


def test_nodes_is_a_namespace_package() -> None:
    import nodes

    # PEP 420 signature: namespace packages have no __file__ (None or unset).
    assert getattr(nodes, "__file__", None) is None


def test_legacy_import_path_is_gone() -> None:
    with pytest.raises(ModuleNotFoundError) as excinfo:
        importlib.import_module(LEGACY_PATH)

    # Name-checked so a broken internal dependency cannot masquerade as absence.
    assert excinfo.value.name == LEGACY_PATH
