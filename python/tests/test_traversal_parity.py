from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.core.corpus import Corpus

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "check-corpus"
ORACLE = FIXTURES / "traversal.oracle.json"


def test_membership_traversal_matches_committed_oracle(tmp_path):
    # Cross-language freeze: same fixture + oracle as the TypeScript kernel. Traversal
    # is registry-independent, so the corpus is constructed without a registry.
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    corpus = Corpus(corpus_dir)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle, "oracle must not be empty"
    for row in oracle:
        assert getattr(corpus, row["op"])(row["ref"]) == row["expect"], f"{row['op']}({row['ref']})"
