from __future__ import annotations

import json
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.search import score_key

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "search-corpus"
ORACLE = FIXTURES / "search.oracle.json"

QUERIES = ["search", "documents ranking", "relevance"]


def main() -> None:
    corpus = Corpus(CORPUS)
    cases = []
    for query in QUERIES:
        hits = corpus.search(query)
        cases.append(
            {"query": query, "hits": [{"id": h.id, "score": score_key(h.score)} for h in hits]}
        )
    ORACLE.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
