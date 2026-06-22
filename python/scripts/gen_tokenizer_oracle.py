from __future__ import annotations

import json
from pathlib import Path

from nodes.kernel.search import tokenize

ORACLE = Path(__file__).parent.parent.parent / "fixtures" / "search.tokenizer.json"

INPUTS = [
    "",
    "   \t\n ",
    "The Quick Brown Fox",
    "the THE The",
    "well-known",
    "state_of_art",
    "don't",
    "3.14 and 2",
    "café",            # composed U+00E9
    "café",      # decomposed e + combining acute
    "Hello МИР",       # Cyrillic
    "hello 世界",       # CJK
    "data\U0001D7D9point",  # non-BMP MATHEMATICAL DOUBLE-STRUCK DIGIT ONE inside a token
]


def main() -> None:
    cases = [{"input": text, "tokens": tokenize(text)} for text in INPUTS]
    ORACLE.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
