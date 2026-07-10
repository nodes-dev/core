from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.registry import Registry
from nodes.kernel.shapes import register_builtin_shapes
from nodes.vocab.kinds import register_knowledge_vocab

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "check-corpus"
ORACLE = FIXTURES / "check.oracle.json"


def test_check_findings_match_committed_oracle(tmp_path):
    # Cross-language freeze: Corpus.check over the committed fixture corpus must
    # reproduce the committed findings oracle exactly (severity, code, ref, detail).
    # The TypeScript kernel asserts the same fixture + oracle.
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    reg = Registry()
    register_builtin_shapes(reg)
    register_knowledge_vocab(reg)
    corpus = Corpus(corpus_dir, registry=reg)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle, "oracle must not be empty"
    actual = [{"severity": f.severity, "code": f.code, "ref": f.ref, "detail": f.detail} for f in corpus.check()]
    assert actual == oracle


def test_check_corpus_has_seven_nodes(tmp_path):
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    assert len(Corpus(corpus_dir).all()) == 7
