from __future__ import annotations

from nodes.kernel.relations import Relation

ABOUT = "about"      # any node -> topic
CITES = "cites"      # any node -> paper/book/dataset
ANSWERS = "answers"  # note/idea -> question
ASKS = "asks"        # any node -> question (raises one)
REFINES = "refines"  # any node -> node (builds on / supersedes)


def about(source: str, target: str) -> Relation:
    """`source` is about `target` (a topic)."""
    return Relation(source=source, predicate=ABOUT, target=target)


def cites(source: str, target: str) -> Relation:
    """`source` cites `target` (a paper/book/dataset)."""
    return Relation(source=source, predicate=CITES, target=target)


def answers(source: str, target: str) -> Relation:
    """`source` (a note/idea) answers `target` (a question)."""
    return Relation(source=source, predicate=ANSWERS, target=target)


def asks(source: str, target: str) -> Relation:
    """`source` raises `target` (a question)."""
    return Relation(source=source, predicate=ASKS, target=target)


def refines(source: str, target: str) -> Relation:
    """`source` refines / supersedes `target`."""
    return Relation(source=source, predicate=REFINES, target=target)
