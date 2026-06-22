import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { CollisionError, RefError } from "./errors.js";
import { nodeFromMarkdown, nodeToMarkdown } from "./frontmatter.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";
import { MEMBERSHIP } from "./shapes.js";

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

  allNodes(): Node[] {
    return this.markdownPaths()
      .sort()
      .map((p) => nodeFromMarkdown(readFileSync(p, "utf-8")));
  }

  private claimedIds(node: Node): Set<string> {
    return new Set([node.id, ...node.deprecatedIds]);
  }

  private assertNoIdentityCollision(node: Node): void {
    const claimed = this.claimedIds(node);
    for (const existing of this.allNodes()) {
      const sameLiveIdentity = existing.id === node.id && existing.uid === node.uid;
      if (existing.uid === node.uid && existing.id !== node.id) {
        throw new CollisionError(
          `uid ${JSON.stringify(node.uid)} already belongs to live id ${JSON.stringify(existing.id)}; use rename()`,
        );
      }
      if (sameLiveIdentity) continue;
      const existingClaims = this.claimedIds(existing);
      const overlap = [...claimed].filter((c) => existingClaims.has(c)).sort();
      if (overlap.length > 0) {
        throw new CollisionError(`identity claims already in use: ${JSON.stringify(overlap)}`);
      }
    }
  }

  private writeFileRaw(node: Node): string {
    const path = this.pathFor(node.id);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, nodeToMarkdown(node), "utf-8");
    return path;
  }

  write(node: Node): string {
    this.assertNoIdentityCollision(node);
    return this.writeFileRaw(node);
  }

  resolve(ref: string): Node {
    const path = this.pathFor(ref);
    if (existsSync(path) && statSync(path).isFile()) {
      return nodeFromMarkdown(readFileSync(path, "utf-8"));
    }
    for (const n of this.allNodes()) {
      if (n.deprecatedIds.includes(ref)) return n;
    }
    throw new RefError(`no node resolves ref ${JSON.stringify(ref)}`);
  }

  read(nodeId: string): Node {
    return this.resolve(nodeId);
  }

  delete(nodeId: string): void {
    const path = this.pathFor(nodeId);
    if (!(existsSync(path) && statSync(path).isFile())) {
      throw new RefError(`no node at ${JSON.stringify(nodeId)}`);
    }
    rmSync(path);
  }

  private idOwnerUid(nodeId: string): string | null {
    for (const n of this.allNodes()) {
      if (n.id === nodeId || n.deprecatedIds.includes(nodeId)) return n.uid;
    }
    return null;
  }

  rename(oldId: string, newId: string): Node {
    if (this.idOwnerUid(newId) !== null) {
      throw new CollisionError(`target id ${JSON.stringify(newId)} already in use`);
    }
    const node = this.read(oldId);
    const oldPath = this.pathFor(oldId);
    node.id = newId;
    node.kind = NodeId.parse(newId).kind;
    if (!node.deprecatedIds.includes(oldId)) node.deprecatedIds.push(oldId);

    const newPath = this.writeFileRaw(node); // write new FIRST — no data-loss window
    if (oldPath !== newPath && existsSync(oldPath) && statSync(oldPath).isFile()) {
      rmSync(oldPath); // then remove old
    }
    this.rewriteInbound(oldId, newId);
    return node;
  }

  private rewriteInbound(oldId: string, newId: string): void {
    for (const other of this.allNodes()) {
      if (other.id === newId) continue;
      let changed = this.rewriteRelations(other, oldId, newId);
      changed = this.rewriteMembership(other, oldId, newId) || changed;
      if (changed) this.write(other);
    }
  }

  private rewriteRelations(node: Node, oldId: string, newId: string): boolean {
    let changed = false;
    for (const rel of node.relations) {
      if (rel.target === oldId) {
        rel.target = newId;
        changed = true;
      }
      if (rel.source === oldId) {
        rel.source = newId;
        changed = true;
      }
    }
    return changed;
  }

  private rewriteMembership(node: Node, oldId: string, newId: string): boolean {
    const mem = node.facets[MEMBERSHIP];
    if (mem === undefined || mem === null || typeof mem !== "object") return false;
    const m = mem as Record<string, unknown>;
    let changed = false;

    const members = m.members;
    if (Array.isArray(members)) {
      let mchanged = false;
      const updated = members.map((x) => {
        if (x === oldId) {
          mchanged = true;
          return newId;
        }
        return x;
      });
      if (mchanged) {
        m.members = updated;
        changed = true;
      }
    } else if (members !== null && typeof members === "object") {
      const obj = members as Record<string, unknown>;
      for (const key of Object.keys(obj)) {
        if (obj[key] === oldId) {
          obj[key] = newId;
          changed = true;
        }
      }
    }

    const edges = m.edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (e.source === oldId) {
            e.source = newId;
            changed = true;
          }
          if (e.target === oldId) {
            e.target = newId;
            changed = true;
          }
        }
      }
    }
    return changed;
  }
}
