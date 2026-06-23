import { createHash } from "node:crypto";
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

export interface SimilarHit {
  id: string;
  uid: string;
  score: number;
}
