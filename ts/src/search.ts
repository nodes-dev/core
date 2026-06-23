import { CollisionError } from "./errors.js";
import type { Node } from "./node.js";
import { scoreKey } from "./ranking.js";

/** Fixed English stop-word list (33 words), frozen by the tokenizer oracle. */
export const STOP_WORDS: ReadonlySet<string> = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "but",
  "by",
  "for",
  "if",
  "in",
  "into",
  "is",
  "it",
  "no",
  "not",
  "of",
  "on",
  "or",
  "such",
  "that",
  "the",
  "their",
  "then",
  "there",
  "these",
  "they",
  "this",
  "to",
  "was",
  "will",
  "with",
]);

// Maximal runs of Unicode alphanumerics (\p{L} ∪ \p{N}); everything else separates.
// This is the parity twin of Python's re.findall(r"[^\W_]+", s).
const TOKEN_RE = /[\p{L}\p{N}]+/gu;

// Compare by Unicode code point. Array.from iterates by code point (surrogate-pair aware),
// so this is the explicit comparator the spec requires instead of default UTF-16 sort.
function compareCodepoints(a: string, b: string): number {
  const ca = Array.from(a);
  const cb = Array.from(b);
  const len = Math.min(ca.length, cb.length);
  for (let i = 0; i < len; i++) {
    const x = ca[i].codePointAt(0) as number;
    const y = cb[i].codePointAt(0) as number;
    if (x !== y) return x - y;
  }
  return ca.length - cb.length;
}

/** Sort by Unicode code-point order — mirrors Python's default string sort (which is
 * already code-point order) and is the cross-language ordering contract. */
export function codepointSorted(values: Iterable<string>): string[] {
  return [...values].sort(compareCodepoints);
}

/** NFC-normalize, lowercase, split into Unicode-alphanumeric runs, drop stop words.
 * Document tokenization keeps duplicates; query-side dedup happens in SearchIndex.search. */
export function tokenize(text: string): string[] {
  const normalized = text.normalize("NFC").toLowerCase();
  const matches = normalized.match(TOKEN_RE) ?? [];
  return matches.filter((tok) => !STOP_WORDS.has(tok));
}

export const K1 = 1.5;
export const B = 0.75;
export const TITLE_BOOST = 2.0;
export const BODY_BOOST = 1.0;

export interface SearchHit {
  id: string;
  uid: string;
  score: number;
  matchedTerms: string[];
}

/** In-memory inverted index over node title+body. Pure data; no file I/O. */
export class SearchIndex {
  postings = new Map<string, Map<string, [number, number]>>(); // term -> uid -> [titleTf, bodyTf]
  lengths = new Map<string, [number, number]>(); // uid -> [titleLen, bodyLen]
  idByUid = new Map<string, string>();
  totalTitle = 0;
  totalBody = 0;

  get n(): number {
    return this.lengths.size;
  }

  static build(nodes: Iterable<Node>): SearchIndex {
    const idx = new SearchIndex();
    for (const node of nodes) {
      if (idx.lengths.has(node.uid)) {
        throw new CollisionError(`duplicate uid ${JSON.stringify(node.uid)} in corpus`);
      }
      idx.upsert(node);
    }
    return idx;
  }

  private static counts(tokens: string[]): Map<string, number> {
    const counts = new Map<string, number>();
    for (const tok of tokens) counts.set(tok, (counts.get(tok) ?? 0) + 1);
    return counts;
  }

  upsert(node: Node): void {
    if (this.lengths.has(node.uid)) this.drop(node.uid);
    const titleTokens = tokenize(node.title);
    const bodyTokens = tokenize(node.body);
    const titleCounts = SearchIndex.counts(titleTokens);
    const bodyCounts = SearchIndex.counts(bodyTokens);
    const terms = new Set<string>([...titleCounts.keys(), ...bodyCounts.keys()]);
    for (const term of terms) {
      let docs = this.postings.get(term);
      if (docs === undefined) {
        docs = new Map<string, [number, number]>();
        this.postings.set(term, docs);
      }
      docs.set(node.uid, [titleCounts.get(term) ?? 0, bodyCounts.get(term) ?? 0]);
    }
    this.lengths.set(node.uid, [titleTokens.length, bodyTokens.length]);
    this.idByUid.set(node.uid, node.id);
    this.totalTitle += titleTokens.length;
    this.totalBody += bodyTokens.length;
  }

  remove(uid: string): void {
    this.drop(uid);
  }

  search(query: string, limit?: number): SearchHit[] {
    if (limit !== undefined && (!Number.isInteger(limit) || limit <= 0)) {
      throw new RangeError(`limit must be a positive integer or undefined, got ${JSON.stringify(limit)}`);
    }
    const terms = codepointSorted(new Set(tokenize(query))); // dedup + code-point order
    if (terms.length === 0) return [];

    const n = this.n;
    const avgTitle = n > 0 ? this.totalTitle / n : 0;
    const avgBody = n > 0 ? this.totalBody / n : 0;

    const scores = new Map<string, number>();
    const matched = new Map<string, string[]>();
    for (const term of terms) {
      const docs = this.postings.get(term);
      if (docs === undefined) continue;
      const df = docs.size;
      const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
      for (const [uid, [titleTf, bodyTf]] of docs) {
        const [titleLen, bodyLen] = this.lengths.get(uid) as [number, number];
        let tfPrime = 0;
        if (titleTf > 0) {
          const denom = avgTitle > 0 ? 1 - B + B * (titleLen / avgTitle) : 1;
          tfPrime += (TITLE_BOOST * titleTf) / denom;
        }
        if (bodyTf > 0) {
          const denom = avgBody > 0 ? 1 - B + B * (bodyLen / avgBody) : 1;
          tfPrime += (BODY_BOOST * bodyTf) / denom;
        }
        scores.set(uid, (scores.get(uid) ?? 0) + (idf * (K1 + 1) * tfPrime) / (K1 + tfPrime));
        const m = matched.get(uid);
        if (m === undefined) matched.set(uid, [term]);
        else m.push(term);
      }
    }

    const hits: SearchHit[] = [];
    for (const [uid, score] of scores) {
      hits.push({
        id: this.idByUid.get(uid) as string,
        uid,
        score,
        matchedTerms: codepointSorted(matched.get(uid) as string[]),
      });
    }
    hits.sort((a, b) => {
      const ka = scoreKey(a.score);
      const kb = scoreKey(b.score);
      if (ka !== kb) return kb - ka; // scoreKey descending
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; // id ascending
    });
    return limit === undefined ? hits : hits.slice(0, limit);
  }

  private drop(uid: string): void {
    const lengths = this.lengths.get(uid);
    if (lengths === undefined) return;
    this.totalTitle -= lengths[0];
    this.totalBody -= lengths[1];
    this.lengths.delete(uid);
    this.idByUid.delete(uid);
    for (const [term, docs] of [...this.postings]) {
      if (docs.has(uid)) {
        docs.delete(uid);
        if (docs.size === 0) this.postings.delete(term);
      }
    }
  }
}
