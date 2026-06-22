from __future__ import annotations

import json
from pathlib import Path

from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown

from tests._canonical import to_canonical

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
SOURCE = FIXTURES / "gene_phf19.md"
ORACLE = FIXTURES / "gene_phf19.canonical.json"
PY_EMIT = FIXTURES / "gene_phf19.py-emit.md"


def _node():
    return node_from_markdown(SOURCE.read_text(encoding="utf-8"))


def test_python_parse_matches_oracle():
    assert to_canonical(_node()) == json.loads(ORACLE.read_text(encoding="utf-8"))


def test_py_emit_fixture_is_current():
    # Regenerate-and-diff currency guard: the committed py-emit fixture must equal
    # what the CURRENT emitter produces. On drift this fails — regenerate the file.
    assert PY_EMIT.read_text(encoding="utf-8") == node_to_markdown(_node())


def test_py_emit_round_trips_to_oracle():
    assert to_canonical(node_from_markdown(PY_EMIT.read_text(encoding="utf-8"))) == json.loads(
        ORACLE.read_text(encoding="utf-8")
    )
