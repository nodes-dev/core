import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { CollisionError } from "./errors.js";
import type { Node } from "./node.js";
import { scoreKey } from "./ranking.js";

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

export interface VectorSnapshot {
  namespace: string | null;
  dim: number | null;
  vectors: Record<string, number[]>;
  idByUid: Record<string, string>;
  hashByUid: Record<string, string>;
}

function validateK(k?: number): void {
  if (k !== undefined && (!Number.isInteger(k) || k <= 0)) {
    throw new RangeError(`k must be a positive integer or undefined, got ${JSON.stringify(k)}`);
  }
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

  toDict(): VectorSnapshot {
    return {
      namespace: this.namespace,
      dim: this.vectors.size > 0 ? this.dim : null,
      vectors: Object.fromEntries([...this.vectors].map(([uid, vec]) => [uid, [...vec]])),
      idByUid: Object.fromEntries(this.idByUid),
      hashByUid: Object.fromEntries(this.hashByUid),
    };
  }

  static fromDict(d: unknown): VectorIndex {
    if (typeof d !== "object" || d === null) throw new Error("vector snapshot: document must be an object");
    const raw = d as Record<string, unknown>;
    for (const key of ["namespace", "dim", "vectors", "idByUid", "hashByUid"]) {
      if (!(key in raw)) throw new Error(`vector snapshot: missing ${key}`);
    }
    const { namespace, dim } = raw;
    if (typeof raw.vectors !== "object" || raw.vectors === null)
      throw new Error("vector snapshot: vectors must be an object");
    if (typeof raw.idByUid !== "object" || raw.idByUid === null)
      throw new Error("vector snapshot: idByUid must be an object");
    if (typeof raw.hashByUid !== "object" || raw.hashByUid === null)
      throw new Error("vector snapshot: hashByUid must be an object");
    const vectorsRaw = raw.vectors as Record<string, unknown>;
    const idByUid = new Map<string, string>();
    for (const [uid, id] of Object.entries(raw.idByUid as Record<string, unknown>)) {
      if (typeof id !== "string") throw new Error("vector snapshot: idByUid must map string uids to string ids");
      idByUid.set(uid, id);
    }
    const hashByUid = new Map<string, string>();
    for (const [uid, h] of Object.entries(raw.hashByUid as Record<string, unknown>)) {
      if (typeof h !== "string") throw new Error("vector snapshot: hashByUid values must be strings");
      validateTextHash(h);
      hashByUid.set(uid, h);
    }
    const vectorUids = Object.keys(vectorsRaw);
    const sameSet =
      vectorUids.length === idByUid.size &&
      vectorUids.length === hashByUid.size &&
      vectorUids.every((uid) => idByUid.has(uid) && hashByUid.has(uid));
    if (!sameSet) throw new Error("vector snapshot: vectors/idByUid/hashByUid uid sets differ");

    const hasVectors = vectorUids.length > 0;
    if (hasVectors) {
      if (typeof namespace !== "string")
        throw new Error("vector snapshot: namespace must be a string when vectors are present");
      validateNamespace(namespace);
      if (typeof dim !== "number" || !Number.isInteger(dim) || dim <= 0) {
        throw new Error("vector snapshot: dim must be a positive integer when vectors are present");
      }
    } else if (dim !== null) {
      throw new Error("vector snapshot: dim must be null when there are no vectors");
    } else if (namespace !== null) {
      if (typeof namespace !== "string") throw new Error("vector snapshot: namespace must be a string when non-null");
      validateNamespace(namespace);
    }

    const vectors = new Map<string, Vector>();
    for (const [uid, rawVec] of Object.entries(vectorsRaw)) {
      if (!Array.isArray(rawVec)) throw new Error("vector snapshot: vector must be an array");
      for (const x of rawVec) {
        if (typeof x !== "number" || !Number.isFinite(x))
          throw new Error("vector snapshot: vector contains a non-finite value");
      }
      const vec = rawVec as number[];
      if (vec.length !== dim) throw new Error("vector snapshot: vector length != dim");
      const norm = Math.sqrt(vec.reduce((s, x) => s + x * x, 0));
      if (Math.abs(norm - 1) > 1e-9) throw new Error("vector snapshot: stored vector must be L2-normalized");
      vectors.set(uid, [...vec]);
    }

    const idx = new VectorIndex();
    idx.namespace = (namespace as string | null) ?? null;
    idx.vectors = vectors;
    idx.idByUid = idByUid;
    idx.hashByUid = hashByUid;
    idx.dim = (dim as number | null) ?? null;
    return idx;
  }

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

  queryVector(vec: Vector, k?: number): SimilarHit[] {
    validateK(k);
    return this.rank(this.prepareQuery(vec), k, null);
  }

  similar(uid: string, k?: number): SimilarHit[] {
    validateK(k);
    const vec = this.vectors.get(uid);
    if (vec === undefined) throw new Error(`uid ${JSON.stringify(uid)} not in vector index`);
    return this.rank(vec, k, uid);
  }

  similarText(text: string, embedder: Embedder, k?: number): SimilarHit[] {
    validateK(k);
    if (this.namespace !== null && embedder.cacheNamespace !== this.namespace) {
      throw new RangeError(
        `embedder namespace ${JSON.stringify(embedder.cacheNamespace)} != index namespace ${JSON.stringify(this.namespace)}`,
      );
    }
    const embedded = embedder.embed([text]);
    if (embedded.length !== 1) {
      throw new RangeError(`embedder returned ${embedded.length} vectors for 1 input`);
    }
    return this.queryVector(embedded[0], k);
  }

  private prepareQuery(vec: Vector): Vector {
    validateFinite(vec);
    if (this.dim !== null && vec.length !== this.dim) {
      throw new RangeError(`query dim ${vec.length} != index dim ${this.dim}`);
    }
    return normalize(vec);
  }

  private rank(queryVec: Vector, k: number | undefined, excludeUid: string | null): SimilarHit[] {
    const hits: SimilarHit[] = [];
    for (const [uid, vec] of this.vectors) {
      if (uid === excludeUid) continue;
      let dot = 0;
      for (let i = 0; i < queryVec.length; i++) dot += queryVec[i] * vec[i];
      hits.push({ id: this.idByUid.get(uid) as string, uid, score: dot });
    }
    hits.sort((a, b) => {
      const ka = scoreKey(a.score);
      const kb = scoreKey(b.score);
      if (ka !== kb) return kb - ka; // scoreKey descending
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; // id ascending
    });
    return k === undefined ? hits : hits.slice(0, k);
  }
}
