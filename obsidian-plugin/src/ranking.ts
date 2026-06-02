/**
 * src/ranking.ts — forgetting-curve ranking (U37, FR-R9).
 *
 * A pure, deterministic re-rank over the core's hits: combine relevance (score)
 * with staleness (down-weight recently-touched notes) so genuinely-forgotten
 * notes surface above ones you just edited. Staleness comes from the engine's
 * per-Hit `recency` (epoch-seconds git committer-time) when present and non-null,
 * otherwise the note's local mtime fallback. The decay is computed here, client
 * side — the engine emits a raw timestamp, not a pre-decayed score.
 *
 * `now` is injected so the function is fully deterministic (and testable without
 * a clock). No vault writes, no I/O — read-only consumption only.
 */
import type { Hit } from "./core";

export interface RankedHit extends Hit {
  /** 0..1 — 0 = just touched, →1 = long forgotten. */
  staleness: number;
  /** Final ranking score after the forgetting-curve reweight. */
  rankScore: number;
  /** Where the staleness came from, for provenance/tooltips. */
  recencySource: "engine" | "mtime" | "unknown";
}

export interface RankOptions {
  /** Epoch seconds "now" — injected for determinism. */
  now: number;
  /** Staleness half-life in days. */
  halfLifeDays: number;
  /** 0..1 — how strongly staleness reweights relevance. */
  stalenessWeight: number;
  /** Local mtime (epoch seconds) for a path when the engine recency is absent. */
  mtimeFallback?: (path: string) => number | null;
}

function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

/**
 * Staleness in [0,1): 0 at age 0, 0.5 at one half-life, →1 as age grows.
 * age = now − recency (epoch seconds), floored at 0.
 */
export function staleness(recencySec: number, now: number, halfLifeDays: number): number {
  const ageDays = Math.max(0, (now - recencySec) / 86400);
  const hl = Math.max(halfLifeDays, 1e-4);
  return 1 - Math.pow(2, -ageDays / hl);
}

function pickRecency(
  h: Hit,
  fallback?: (path: string) => number | null,
): { value: number | null; source: RankedHit["recencySource"] } {
  if (typeof h.recency === "number") return { value: h.recency, source: "engine" };
  const fb = fallback?.(h.path);
  if (typeof fb === "number") return { value: fb, source: "mtime" };
  return { value: null, source: "unknown" };
}

/**
 * Re-rank by relevance × staleness. Equal-relevance hits sort staler-first; a
 * fresh highly-relevant note can be overtaken by a stale slightly-less-relevant
 * one when stalenessWeight is high enough. Stable, deterministic given `now`.
 */
export function rankHits(hits: Hit[], opts: RankOptions): RankedHit[] {
  const w = clamp01(opts.stalenessWeight);
  const ranked: RankedHit[] = hits.map((h) => {
    const { value, source } = pickRecency(h, opts.mtimeFallback);
    const s = value == null ? 0 : staleness(value, opts.now, opts.halfLifeDays);
    // Keep relevance primary; lift staler notes by the staleness weight.
    const rankScore = h.score * (1 - w) + h.score * s * w;
    return { ...h, staleness: s, rankScore, recencySource: source };
  });
  // Sort by reweighted score desc; ties broken by raw relevance desc, then path
  // for full determinism.
  ranked.sort(
    (a, b) =>
      b.rankScore - a.rankScore ||
      b.score - a.score ||
      a.path.localeCompare(b.path),
  );
  return ranked;
}
