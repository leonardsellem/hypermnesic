/**
 * src/surfaces/render.ts — the recall result list (U38/KTD1).
 *
 * The status-bar popover and the opt-in sidebar both render through this one
 * function. Each note reference is rendered by the shared reference-row
 * primitive (renderReference) so links, Page-preview hover, the context menu,
 * insertion, and the local/non-local branch are inherited; this file adds only
 * recall chrome — channel chips and staleness — around each row (KTD2). Pure DOM
 * (createEl, never innerHTML); navigation opens existing notes only — no writes.
 */
import { HoverParent } from "obsidian";
import type { RankedHit } from "../ranking";
import { RecallState, StateSnapshot, renderTrustBadge } from "../state";
import {
  ReferenceRowDeps,
  enableRovingFocus,
  renderReference,
  resolveReference,
} from "./reference";

export interface RenderDeps extends ReferenceRowDeps {
  /** Optional reinvention-nudge renderer (U40), prepended to the list. */
  renderNudge?(host: HTMLElement, snapshot: StateSnapshot, hoverParent: HoverParent | null): void;
}

/** States that still render the hit list (a banner is layered above it). */
const SHOWS_LIST = new Set<RecallState>(["results", "degraded", "stale", "reindex"]);

const CHANNEL_TITLE: Record<string, string> = {
  lexical: "keyword",
  dense: "meaning",
  doc: "document",
};

function stalenessLabel(hit: RankedHit): { text: string; title: string } {
  if (hit.recencySource === "unknown") return { text: "·", title: "recency unknown" };
  const source = hit.recencySource === "engine" ? "git write-time" : "local file time";
  const pct = Math.round(hit.staleness * 100);
  const text = hit.staleness > 0.66 ? "long unseen" : hit.staleness > 0.33 ? "a while" : "recent";
  return { text, title: `staleness ${pct}% (${source})` };
}

export function renderResultList(
  container: HTMLElement,
  model: StateSnapshot,
  deps: RenderDeps,
  hoverParent: HoverParent | null = null,
): void {
  container.empty();
  container.setAttribute("role", "region");
  container.setAttribute("aria-label", "hypermnesic related notes");

  // Persistent read-only / trust badge on every surface (FR-R19).
  renderTrustBadge(container);

  const status = container.createEl("div", { cls: "hypermnesic-status" });
  status.setAttribute("aria-live", "polite");
  if (model.banner) status.setText(model.banner);

  if (!SHOWS_LIST.has(model.state)) return;
  const result = model.result;
  if (!result || result.hits.length === 0) {
    status.setText("nothing related yet");
    return;
  }

  if (deps.renderNudge) deps.renderNudge(container, model, hoverParent);

  const list = container.createEl("ul", { cls: "hypermnesic-related-list" });
  list.setAttribute("role", "list");
  const sourcePath = result.sourcePath;
  const focusables: HTMLElement[] = [];
  result.hits.forEach((hit) => focusables.push(renderHit(list, hit, deps, sourcePath, hoverParent)));
  enableRovingFocus(list, focusables);
}

function renderHit(
  list: HTMLElement,
  hit: RankedHit,
  deps: RenderDeps,
  sourcePath: string,
  hoverParent: HoverParent | null,
): HTMLElement {
  const li = list.createEl("li", { cls: "hypermnesic-hit" });
  li.setAttribute("role", "listitem");

  const resolved = resolveReference(
    deps.app,
    { path: hit.path, heading: hit.heading, snippet: hit.snippet },
    sourcePath,
  );
  const focusable = renderReference(li, resolved, sourcePath, deps, hoverParent);

  const meta = li.createSpan({ cls: "hypermnesic-hit-meta" });
  for (const channel of hit.channels) {
    const label = CHANNEL_TITLE[channel] ?? channel;
    const chip = meta.createSpan({ cls: `hypermnesic-chip hypermnesic-chip-${channel}`, text: label });
    chip.setAttribute("title", label);
    chip.setAttribute("aria-label", `${label} match`);
  }
  const stale = stalenessLabel(hit);
  const tag = meta.createSpan({ cls: "hypermnesic-staleness", text: stale.text });
  tag.setAttribute("title", stale.title);
  tag.setAttribute("aria-label", stale.title);

  return focusable;
}
