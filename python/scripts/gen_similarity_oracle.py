from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.ranking import score_key
from nodes.kernel.similarity import Vector, embed_text

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


def build_table(data: dict, nodes: list) -> dict[str, Vector]:
    by_id = {d["id"]: tuple(d["vector"]) for d in data["documents"]}
    table: dict[str, Vector] = {embed_text(n): by_id[n.id] for n in nodes}
    for q in data["queries"]:
        table[q["text"]] = tuple(q["vector"])
    return table


def _hits(hits) -> list[dict]:
    return [{"id": h.id, "score": score_key(h.score)} for h in hits]


def main() -> None:
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "similarity-corpus"
        shutil.copytree(CORPUS, dst)
        nodes = Corpus(dst).all()  # plain read, no embedder
        emb = LookupEmbedder(build_table(data, nodes))
        corpus = Corpus(dst, embedder=emb)
        cases = {
            "similar": [{"ref": d["id"], "hits": _hits(corpus.similar(d["id"]))} for d in data["documents"]],
            "query_vector": [
                {"text": q["text"], "hits": _hits(corpus.query_vector(tuple(q["vector"])))}
                for q in data["queries"]
            ],
            "similar_text": [
                {"text": q["text"], "hits": _hits(corpus.similar_text(q["text"]))} for q in data["queries"]
            ],
        }
    ORACLE.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
