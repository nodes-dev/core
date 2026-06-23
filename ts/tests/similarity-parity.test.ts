import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import type { Node } from "../src/node.js";
import { scoreKey } from "../src/ranking.js";
import { type Embedder, type SimilarHit, type Vector, embedText } from "../src/similarity.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));
const CORPUS = join(FIXTURES, "similarity-corpus");
const VECTORS = join(FIXTURES, "similarity.vectors.json");
const ORACLE = join(FIXTURES, "similarity.oracle.json");

interface VectorsFile {
  documents: { id: string; vector: number[] }[];
  queries: { text: string; vector: number[] }[];
}
interface OracleCase {
  ref?: string;
  text?: string;
  hits: { id: string; score: number }[];
}
interface OracleFile {
  similar: OracleCase[];
  query_vector: OracleCase[];
  similar_text: OracleCase[];
}

class LookupEmbedder implements Embedder {
  readonly cacheNamespace = "fixture-v1";
  private table: Map<string, Vector>;
  constructor(table: Map<string, Vector>) {
    this.table = table;
  }
  embed(texts: string[]): Vector[] {
    return texts.map((t) => {
      const v = this.table.get(t);
      if (v === undefined) throw new Error(`no vector for ${JSON.stringify(t)}`);
      return v;
    });
  }
}

function buildTable(data: VectorsFile, nodes: Node[]): Map<string, Vector> {
  const byId = new Map(data.documents.map((d) => [d.id, d.vector]));
  const table = new Map<string, Vector>();
  for (const n of nodes) {
    const vec = byId.get(n.id);
    if (vec === undefined) throw new Error(`no frozen vector for ${n.id}`);
    table.set(embedText(n), vec);
  }
  for (const q of data.queries) table.set(q.text, q.vector);
  return table;
}

function rounded(hits: SimilarHit[]): { id: string; score: number }[] {
  return hits.map((h) => ({ id: h.id, score: scoreKey(h.score) }));
}

function expected(hits: { id: string; score: number }[]): { id: string; score: number }[] {
  return hits.map((h) => ({ id: h.id, score: scoreKey(h.score) }));
}

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-sim-parity-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("cross-language similarity oracle", () => {
  it("the fixture corpus has four topics", () => {
    cpSync(CORPUS, root, { recursive: true });
    expect(new Corpus(root).all().length).toBe(4);
  });

  it("TS Corpus similarity over the frozen fixtures matches the shared oracle", () => {
    cpSync(CORPUS, root, { recursive: true });
    const data = JSON.parse(readFileSync(VECTORS, "utf-8")) as VectorsFile;
    const oracle = JSON.parse(readFileSync(ORACLE, "utf-8")) as OracleFile;
    expect(oracle.similar.length).toBeGreaterThan(0);
    expect(oracle.query_vector.length).toBeGreaterThan(0);
    expect(oracle.similar_text.length).toBeGreaterThan(0);

    const nodes = new Corpus(root).all();
    // guard: every corpus node has a frozen document vector
    const ids = new Set(nodes.map((n) => n.id));
    expect(ids).toEqual(new Set(data.documents.map((d) => d.id)));

    const emb = new LookupEmbedder(buildTable(data, nodes));
    const corpus = new Corpus(root, undefined, emb);
    const queryVecByText = new Map(data.queries.map((q) => [q.text, q.vector]));

    for (const c of oracle.similar) {
      expect(rounded(corpus.similar(c.ref as string))).toEqual(expected(c.hits));
    }
    for (const c of oracle.query_vector) {
      const vec = queryVecByText.get(c.text as string) as Vector;
      expect(rounded(corpus.queryVector(vec))).toEqual(expected(c.hits));
    }
    for (const c of oracle.similar_text) {
      expect(rounded(corpus.similarText(c.text as string))).toEqual(expected(c.hits));
    }
  });
});
