from __future__ import annotations

from nodes.kernel.registry import KindSpec, Registry
from nodes.vocab.source import SOURCE, require_identifiable_source

NOTE = "note"
IDEA = "idea"
QUESTION = "question"
TOPIC = "topic"
PAPER = "paper"
BOOK = "book"
DATASET = "dataset"

PROSE_KINDS = (NOTE, IDEA, QUESTION, TOPIC)
SOURCE_KINDS = (PAPER, BOOK, DATASET)


def register_knowledge_vocab(reg: Registry) -> None:
    """Register the standard knowledge-vocab kinds onto `reg`.

    Mirrors `nodes.kernel.shapes.register_builtin_shapes`.
    """
    for name in PROSE_KINDS:
        reg.register(KindSpec(name=name))
    for name in SOURCE_KINDS:
        reg.register(
            KindSpec(
                name=name,
                required_facets={SOURCE},
                invariants=[require_identifiable_source],
            )
        )
