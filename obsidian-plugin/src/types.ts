/**
 * src/types.ts — shared settings types. Kept import-free so both core.ts and
 * settings.ts can depend on it without an import cycle.
 */

export interface HypermnesicSettings {
  /** Tailnet MCP endpoint, e.g. http://<tailscale-host>:8848/mcp. EMPTY by
   *  default — nothing transmits off-device until the user sets it (DEP-R17). */
  mcpUrl: string;
  /** Idle pause (ms) before a query may fire. Never per-keystroke. */
  pauseMs: number;
  /** How many related results to request / show. */
  resultCount: number;
  /** Similarity at/above which the reinvention nudge appears. */
  reinventThreshold: number;
  /** Calm-primary status-bar surface. */
  showStatusBar: boolean;
  /** Optional CM6 inline marker on the active block. */
  showGutter: boolean;
  /** Open the opt-in sidebar automatically on load. */
  openSidebarOnLoad: boolean;
  /** Forgetting-curve half-life (days) for the staleness term. */
  recencyHalfLifeDays: number;
  /** 0..1 — how much staleness reweights relevance in ranking. */
  stalenessWeight: number;
}

export const DEFAULT_SETTINGS: HypermnesicSettings = {
  mcpUrl: "", // EMPTY: opt-in off-device send — the empty default never transmits.
  pauseMs: 1500,
  resultCount: 8,
  reinventThreshold: 0.85,
  showStatusBar: true,
  showGutter: false, // CM6 gutter is opt-in (R-3: status-bar is the calm default).
  openSidebarOnLoad: false,
  recencyHalfLifeDays: 30,
  stalenessWeight: 0.35,
};
