from __future__ import annotations

import json
from pathlib import Path

import pytest

from nodes.core.search import STOP_WORDS, tokenize

ORACLE = Path(__file__).parent.parent.parent / "fixtures" / "search.tokenizer.json"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", []),
        ("   \t\n ", []),
        ("The Quick Brown Fox", ["quick", "brown", "fox"]),  # 'the' is a stop word; lowercased
        ("the THE The", []),                                  # all stop words
        ("well-known", ["well", "known"]),                    # hyphen separates
        ("state_of_art", ["state", "art"]),                   # underscore separates; 'of' is a stop word
        ("don't", ["don", "t"]),                              # apostrophe separates
        ("3.14 and 2", ["3", "14", "2"]),                     # '.' separates; 'and' is a stop word
        ("café", ["café"]),                                   # composed (U+00E9)
        ("café", ["café"]),                             # decomposed e + combining acute -> NFC -> café
        ("Hello МИР", ["hello", "мир"]),                      # Cyrillic, lowercased
        ("hello 世界", ["hello", "世界"]),                     # CJK run is one token
    ],
)
def test_tokenize_cases(text, expected):
    assert tokenize(text) == expected


def test_stop_words_count_is_33():
    assert len(STOP_WORDS) == 33
    assert "the" in STOP_WORDS and "with" in STOP_WORDS


def test_tokenizer_matches_committed_oracle():
    # Currency + cross-language freeze: the tokenizer must reproduce every committed
    # oracle case exactly. The later TypeScript port asserts the same file.
    cases = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert cases, "oracle must not be empty"
    for case in cases:
        assert tokenize(case["input"]) == case["tokens"], repr(case["input"])
