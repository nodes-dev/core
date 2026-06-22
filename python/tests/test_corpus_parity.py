from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.kernel.corpus import Corpus

from tests._canonical import to_canonical

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
ORACLE = FIXTURES / "corpus.rename.canonical.json"


def test_corpus_rename_parity(tmp_path):
    corpus_dir = tmp_path / "corpus"
    shutil.copytree(FIXTURES / "corpus", corpus_dir)
    c = Corpus(corpus_dir)
    c.rename("topic:old", "topic:new")
    actual = [to_canonical(n) for n in sorted(c.all(), key=lambda n: n.id)]
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert actual == oracle
