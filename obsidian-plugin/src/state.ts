/**
 * src/state.ts — the interaction-state machine + the visible trust layer (U41,
 * KTD5/FR-R17/R18/R19).
 *
 * Trust is shown, not asserted: one explicit machine drives every surface
 * (idle / loading / results / stale / offline / degraded / reindex / error), a
 * failed refresh after a prior success becomes "stale — as of HH:MM" rather than
 * a silently-frozen list, and a persistent "read-only · tailnet · no text
 * retained" badge rides every render.
 */
import type { CoreResult } from "./core";

export type RecallState =
  | "idle"
  | "loading"
  | "results"
  | "empty"
  | "offline"
  | "degraded"
  | "stale"
  | "reindex"
  | "error";

export interface StateSnapshot {
  result: CoreResult | null;
  state: RecallState;
  /** epoch ms of the last successful result (the as-of stamp). */
  asOf: number | null;
  /** the formatted status line for this snapshot. */
  banner: string;
}

const BASE_MESSAGE: Record<RecallState, string> = {
  idle: "",
  loading: "thinking…",
  results: "",
  empty: "nothing related yet",
  offline: "offline — could not reach the tailnet index",
  degraded: "lexical-only — the semantic channel is down",
  stale: "stale — showing the last result",
  reindex: "stale index — reindex on the master",
  error: "something went wrong reaching the index",
};

function fmtTime(epochMs: number): string {
  const d = new Date(epochMs);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function bannerFor(state: RecallState, asOf: number | null): string {
  if (state === "stale" && asOf) return `stale — as of ${fmtTime(asOf)}`;
  return BASE_MESSAGE[state];
}

function deriveSuccess(result: CoreResult | null): RecallState {
  if (!result) return "empty";
  if (result.manualReindex) return "reindex";
  if (result.degraded) return "degraded";
  return result.hits.length > 0 ? "results" : "empty";
}

/** The single state owner. Surfaces read snapshots; they never compute state. */
export class RecallStateMachine {
  private result: CoreResult | null = null;
  private asOf: number | null = null;
  private state: RecallState = "idle";

  get snapshot(): StateSnapshot {
    return {
      result: this.result,
      state: this.state,
      asOf: this.asOf,
      banner: bannerFor(this.state, this.asOf),
    };
  }

  loading(): StateSnapshot {
    this.state = "loading";
    return this.snapshot;
  }

  success(result: CoreResult | null): StateSnapshot {
    this.result = result;
    if (result) this.asOf = result.asOf;
    this.state = deriveSuccess(result);
    return this.snapshot;
  }

  /** A failed refresh after a prior success is "stale" (the last result stays
   *  visible with its as-of stamp); with no prior result, surface the failure. */
  failure(kind: "offline" | "error"): StateSnapshot {
    this.state = this.result && this.result.hits.length > 0 ? "stale" : kind;
    return this.snapshot;
  }
}

/**
 * The persistent read-only / trust badge (FR-R19). Rendered on every surface so
 * the read-only guarantee is legible in the UI, not just in code. Distinguishable
 * by text (not color alone) and exposed to assistive tech.
 */
export function renderTrustBadge(container: HTMLElement): void {
  const badge = container.createEl("div", { cls: "hypermnesic-trust-badge" });
  badge.setText("read-only · tailnet · no text retained");
  badge.setAttribute(
    "title",
    "This companion only reads: it calls the read tools (search / build_context / " +
      "think) over your tailnet and never writes your vault. It keeps no note text " +
      "between queries.",
  );
  badge.setAttribute("aria-label", "read only, over the tailnet, no note text retained");
}
