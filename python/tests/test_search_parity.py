from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.core.corpus import Corpus
from nodes.core.ranking import score_key

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "search-corpus"
ORACLE = FIXTURES / "search.oracle.json"


def test_search_ranking_matches_committed_oracle(tmp_path):
    # Currency + cross-language freeze: Corpus.search over the committed fixture corpus
    # must reproduce the committed ranking oracle exactly (ranked ids + 6-dp scores).
    # The later TypeScript port asserts the same fixture + oracle.
    corpus_dir = tmp_path / "search-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    corpus = Corpus(corpus_dir)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle, "oracle must not be empty"
    for case in oracle:
        hits = corpus.search(case["query"])
        actual = [{"id": h.id, "score": score_key(h.score)} for h in hits]
        assert actual == case["hits"], case["query"]


def test_search_corpus_has_four_topics(tmp_path):
    corpus_dir = tmp_path / "search-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    assert len(Corpus(corpus_dir).all()) == 4
