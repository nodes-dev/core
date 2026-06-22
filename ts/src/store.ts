import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { RefError } from "./errors.js";
import { nodeFromMarkdown, nodeToMarkdown } from "./frontmatter.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";

/**
 * Pure file mechanics over a corpus directory. No cross-corpus logic.
 * Collision detection, ref resolution, and rename live in `Corpus`/`Index`.
 */
export class Store {
  readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  pathFor(nodeId: string): string {
    const nid = NodeId.parse(nodeId);
    return join(this.root, nid.kind, `${nid.slug.replace(/:/g, "__")}.md`);
  }

  private markdownPaths(): string[] {
    const out: string[] = [];
    const walk = (dir: string): void => {
      if (!existsSync(dir)) return;
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.isFile() && entry.name.endsWith(".md")) out.push(full);
      }
    };
    walk(this.root);
    return out;
  }

  writeFile(node: Node): string {
    const path = this.pathFor(node.id);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, nodeToMarkdown(node), "utf-8");
    return path;
  }

  readFile(nodeId: string): Node {
    const path = this.pathFor(nodeId);
    if (!(existsSync(path) && statSync(path).isFile())) {
      throw new RefError(`no node at ${JSON.stringify(nodeId)}`);
    }
    return nodeFromMarkdown(readFileSync(path, "utf-8"));
  }

  deleteFile(nodeId: string): void {
    const path = this.pathFor(nodeId);
    if (!(existsSync(path) && statSync(path).isFile())) {
      throw new RefError(`no node at ${JSON.stringify(nodeId)}`);
    }
    rmSync(path);
  }

  allNodes(): Node[] {
    return this.markdownPaths()
      .sort()
      .map((p) => nodeFromMarkdown(readFileSync(p, "utf-8")));
  }
}
