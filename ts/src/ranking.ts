/** Half-up rounding to 6 decimal places — the shared ranking/parity key. Used by both the
 * full-text search index and the similarity index, so it lives here rather than in either
 * (neither derived-index facet imports the other). Floor-based half-up is identical in
 * TypeScript and Python (`Math.floor` / `math.floor` agree on negative operands), so it is
 * correct over BM25 (non-negative) and cosine (`[-1, 1]`) scores alike. */
export function scoreKey(score: number): number {
  return Math.floor(score * 1_000_000 + 0.5) / 1_000_000;
}
