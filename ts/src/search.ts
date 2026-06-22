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

/** Half-up rounding to 6 decimal places — the shared ranking/parity key. Scores are
 * non-negative, so this floor-based half-up is correct and identical to Python's. */
export function scoreKey(score: number): number {
  return Math.floor(score * 1_000_000 + 0.5) / 1_000_000;
}

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
