from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.core.corpus import Corpus
from nodes.core.ranking import score_key
from nodes.core.similarity import Vector, embed_text

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "similarity-corpus"
VECTORS = FIXTURES / "similarity.vectors.json"
ORACLE = FIXTURES / "similarity.oracle.json"


class LookupEmbedder:
    cache_namespace = "fixture-v1"

    def __init__(self, table: dict[str, Vector]) -> None:
        self._table = table

    def embed(self, texts: list[str]) -> list[Vector]:
        return [self._table[t] for t in texts]


def _table(data: dict, nodes: list) -> dict[str, Vector]:
    by_id = {d["id"]: tuple(d["vector"]) for d in data["documents"]}
    table: dict[str, Vector] = {embed_text(n): by_id[n.id] for n in nodes}
    for q in data["queries"]:
        table[q["text"]] = tuple(q["vector"])
    return table


def _hits(hits) -> list[dict]:
    return [{"id": h.id, "score": score_key(h.score)} for h in hits]


def test_similarity_corpus_has_four_topics(tmp_path):
    dst = tmp_path / "similarity-corpus"
    shutil.copytree(CORPUS, dst)
    assert len(Corpus(dst).all()) == 4


def test_similarity_ranking_matches_committed_oracle(tmp_path):
    # Currency + cross-language freeze: Corpus similarity over the committed fixture
    # corpus + frozen vectors must reproduce the committed oracle exactly (ranked ids
    # + 6-dp scores). The later TypeScript port asserts the same fixtures + oracle.
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle["similar"] and oracle["query_vector"] and oracle["similar_text"]

    dst = tmp_path / "similarity-corpus"
    shutil.copytree(CORPUS, dst)
    nodes = Corpus(dst).all()
    # guard: every corpus node has a frozen document vector
    by_id = {d["id"]: d for d in data["documents"]}
    assert {n.id for n in nodes} == set(by_id)

    emb = LookupEmbedder(_table(data, nodes))
    corpus = Corpus(dst, embedder=emb)

    for case in oracle["similar"]:
        assert _hits(corpus.similar(case["ref"])) == case["hits"], case["ref"]
    for case in oracle["query_vector"]:
        vec = tuple(next(q for q in data["queries"] if q["text"] == case["text"])["vector"])
        assert _hits(corpus.query_vector(vec)) == case["hits"], case["text"]
    for case in oracle["similar_text"]:
        assert _hits(corpus.similar_text(case["text"])) == case["hits"], case["text"]
