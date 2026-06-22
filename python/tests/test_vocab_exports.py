from __future__ import annotations

import nodes.vocab as vocab


def test_top_level_exports_present():
    assert vocab.register_knowledge_vocab is not None
    assert vocab.NOTE == "note" and vocab.PAPER == "paper" and vocab.DATASET == "dataset"
    assert vocab.SOURCE == "source"
    assert vocab.Source is not None
    assert vocab.source_of is not None and vocab.require_identifiable_source is not None


def test_predicates_module_reachable():
    assert vocab.predicates.CITES == "cites"
