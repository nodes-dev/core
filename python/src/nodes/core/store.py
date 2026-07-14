from __future__ import annotations

from pathlib import Path

from nodes.core.errors import RefError
from nodes.core.frontmatter import node_from_markdown, node_to_markdown
from nodes.core.ids import NodeId
from nodes.core.node import Node
from nodes.core.snapshot import iter_corpus_files


class Store:
    """Pure file mechanics over a corpus directory. No cross-corpus logic.

    Collision detection, ref resolution, and rename live in `Corpus`/`Index`.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, node_id: str) -> Path:
        nid = NodeId.parse(node_id)
        return self.root / nid.kind / f"{nid.slug.replace(':', '__')}.md"

    def write_file(self, node: Node) -> Path:
        path = self.path_for(node.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(node_to_markdown(node), encoding="utf-8")
        return path

    def read_file(self, node_id: str) -> Node:
        path = self.path_for(node_id)
        if not path.is_file():
            raise RefError(f"no node at {node_id!r}")
        return node_from_markdown(path.read_text(encoding="utf-8"))

    def delete_file(self, node_id: str) -> None:
        path = self.path_for(node_id)
        if not path.is_file():
            raise RefError(f"no node at {node_id!r}")
        path.unlink()

    def all_nodes(self) -> list[Node]:
        return [node_from_markdown(f.data.decode("utf-8")) for f in iter_corpus_files(self.root)]
