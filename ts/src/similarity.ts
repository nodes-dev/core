import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { CollisionError } from "./errors.js";
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

/** Return the L2-normalized vector; reject zero-norm and invalid numeric input. */
function normalize(vec: Vector): Vector {
  validateFinite(vec);
  let sumSq = 0;
  for (const x of vec) sumSq += x * x;
  const norm = Math.sqrt(sumSq);
  if (norm === 0) {
    throw new RangeError("cannot normalize a zero-norm vector");
  }
  return vec.map((x) => x / norm);
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

interface PreparedVector {
  readonly textHash: string;
  readonly namespace: string;
  readonly vector: Vector | null; // null => content unchanged (id-only refresh)
}

/** In-memory uid -> L2-normalized vector store with exact cosine ranking. Bound to exactly
 * one embedder namespace and one dimension (cosine across vectors from different models or
 * dimensions is meaningless). */
export class VectorIndex {
  vectors = new Map<string, Vector>();
  idByUid = new Map<string, string>();
  hashByUid = new Map<string, string>();
  dim: number | null = null;
  namespace: string | null = null;

  static build(nodes: Iterable<Node>, embedder: Embedder, cache: VectorCache): VectorIndex {
    const idx = new VectorIndex();
    validateNamespace(embedder.cacheNamespace);
    idx.namespace = embedder.cacheNamespace; // bind even for an empty corpus
    for (const node of nodes) {
      if (idx.hashByUid.has(node.uid)) {
        throw new CollisionError(`duplicate uid ${JSON.stringify(node.uid)} in corpus`);
      }
      idx.upsert(node, embedder, cache);
    }
    return idx;
  }

  /** Resolve + validate the vector WITHOUT mutating index state (cache writes ok). */
  prepare(node: Node, embedder: Embedder, cache: VectorCache): PreparedVector {
    const namespace = embedder.cacheNamespace;
    validateNamespace(namespace);
    if (this.namespace !== null && namespace !== this.namespace) {
      throw new RangeError(
        `embedder namespace ${JSON.stringify(namespace)} != index namespace ${JSON.stringify(this.namespace)}`,
      );
    }
    const text = embedText(node);
    const h = textHash(text);
    if (this.hashByUid.get(node.uid) === h) {
      return { textHash: h, namespace, vector: null };
    }
    let raw = cache.get(namespace, h);
    if (raw === null) {
      const embedded = embedder.embed([text]);
      if (embedded.length !== 1) {
        throw new RangeError(`embedder returned ${embedded.length} vectors for 1 input`);
      }
      raw = embedded[0];
      validateFinite(raw);
      cache.put(namespace, h, raw);
    }
    if (this.dim !== null && raw.length !== this.dim) {
      throw new RangeError(`vector dim ${raw.length} != index dim ${this.dim}`);
    }
    return { textHash: h, namespace, vector: normalize(raw) };
  }

  /** Apply a prepared vector. Infallible: never throws on valid prepared input. */
  commit(node: Node, prepared: PreparedVector): void {
    if (this.namespace === null) this.namespace = prepared.namespace;
    if (prepared.vector === null) {
      this.idByUid.set(node.uid, node.id); // rename / id-only refresh
      return;
    }
    if (this.dim === null) this.dim = prepared.vector.length;
    this.vectors.set(node.uid, prepared.vector);
    this.idByUid.set(node.uid, node.id);
    this.hashByUid.set(node.uid, prepared.textHash);
  }

  upsert(node: Node, embedder: Embedder, cache: VectorCache): void {
    this.commit(node, this.prepare(node, embedder, cache));
  }

  remove(uid: string): void {
    this.vectors.delete(uid);
    this.idByUid.delete(uid);
    this.hashByUid.delete(uid);
  }
}
