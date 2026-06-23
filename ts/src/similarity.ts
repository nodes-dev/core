import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { Node } from "./node.js";

export type Vector = number[];

/** The seam: turns text into vectors. The kernel ships no concrete embedder. */
export interface Embedder {
  readonly cacheNamespace: string;
  embed(texts: string[]): Vector[];
}

/** The frozen per-node embedding input: title and body joined by one blank line. */
export function embedText(node: Node): string {
  return `${node.title}\n\n${node.body}`;
}

/** Content-address key for the vector cache. */
export function textHash(text: string): string {
  return createHash("sha256").update(text, "utf-8").digest("hex");
}

const NAMESPACE_RE = /^[A-Za-z0-9._-]+$/;

/** A cacheNamespace must be a safe single path segment. */
export function validateNamespace(namespace: string): void {
  if (namespace === "." || namespace === ".." || !NAMESPACE_RE.test(namespace)) {
    throw new TypeError(`invalid cacheNamespace ${JSON.stringify(namespace)}`);
  }
}

const TEXT_HASH_RE = /^[0-9a-f]{64}$/;

/** A cache key must be exactly 64 lowercase hex chars (a SHA-256 hexdigest). */
export function validateTextHash(hash: string): void {
  if (!TEXT_HASH_RE.test(hash)) {
    throw new TypeError(`invalid textHash ${JSON.stringify(hash)}`);
  }
}

/** Reject empty / non-numeric / non-finite vectors. Booleans are non-`number` typed,
 * so `typeof x !== "number"` already rejects them. */
function validateFinite(vec: ReadonlyArray<unknown>): void {
  if (vec.length < 1) {
    throw new RangeError("vector must have length >= 1");
  }
  for (const x of vec) {
    if (typeof x !== "number" || !Number.isFinite(x)) {
      throw new TypeError(`vector contains non-finite or non-numeric value ${String(x)}`);
    }
  }
}

export interface SimilarHit {
  id: string;
  uid: string;
  score: number;
}

/** Content-addressed on-disk cache of RAW embedder output, namespaced per embedder.
 * Disposable: deleting the directory just forces re-embedding. All ranking math lives in
 * VectorIndex; this is purely a model-output cache. */
export class VectorCache {
  readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  private pathFor(namespace: string, hash: string): string {
    validateNamespace(namespace);
    validateTextHash(hash);
    return join(this.root, ".nodes-index", "vectors", namespace, `${hash}.json`);
  }

  get(namespace: string, hash: string): Vector | null {
    const path = this.pathFor(namespace, hash);
    if (!existsSync(path)) return null;
    let data: unknown;
    try {
      data = JSON.parse(readFileSync(path, "utf-8"));
    } catch (e) {
      throw new TypeError(`corrupt cache file ${path}: ${(e as Error).message}`);
    }
    if (typeof data !== "object" || data === null || !("dim" in data) || !("vector" in data)) {
      throw new TypeError(`corrupt cache file ${path}: missing dim/vector`);
    }
    const { dim, vector } = data as { dim: unknown; vector: unknown };
    if (!Array.isArray(vector) || vector.length !== dim) {
      throw new TypeError(`corrupt cache file ${path}: dim/vector length mismatch`);
    }
    validateFinite(vector);
    return [...(vector as number[])];
  }

  put(namespace: string, hash: string, vector: Vector): void {
    validateFinite(vector);
    const path = this.pathFor(namespace, hash);
    mkdirSync(dirname(path), { recursive: true });
    const payload = JSON.stringify({ dim: vector.length, vector });
    const tmp = `${path}.tmp`;
    writeFileSync(tmp, payload, "utf-8");
    renameSync(tmp, path);
  }
}
