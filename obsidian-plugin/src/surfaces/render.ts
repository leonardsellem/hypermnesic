/**
 * src/surfaces/render.ts — the shared result renderer (U38/KTD1).
 *
 * The status-bar popover and the opt-in sidebar both render through this one
 * function, so provenance, staleness, keyboard navigation, and aria-live are
 * implemented once and inherited. Pure DOM (createEl, never innerHTML);
 * navigation opens existing notes only — no writes.
 */
import { App } from "obsidian";
import type { CoreResult } from "../core";
import type { RankedHit } from "../ranking";

/** The interaction states surfaces render. The full machine (idle→…→error with
 *  an as-of stamp) is owned by state.ts (U41); render handles the visible form. */
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

export interface RenderDeps {
  app: App;
  /** Read-only navigation to an existing note. */
  openNote(path: string): void;
  /** Optional reinvention-nudge renderer (U40), prepended to the list. */
  renderNudge?(host: HTMLElement, result: CoreResult): void;
}

const STATE_MESSAGE: Record<RecallState, string> = {
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

/** States that still render the hit list (a banner is layered above it). */
const SHOWS_LIST = new Set<RecallState>(["results", "degraded", "stale", "reindex"]);

const CHANNEL_TITLE: Record<string, string> = {
  lexical: "keyword match",
  dense: "semantic (meaning) match",
  doc: "document-level match",
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
  result: CoreResult | null,
  state: RecallState,
  deps: RenderDeps,
): void {
  container.empty();
  container.setAttribute("role", "region");
  container.setAttribute("aria-label", "hypermnesic related notes");

  const status = container.createEl("div", { cls: "hypermnesic-status" });
  status.setAttribute("aria-live", "polite");
  if (STATE_MESSAGE[state]) status.setText(STATE_MESSAGE[state]);

  if (!SHOWS_LIST.has(state)) return;
  if (!result || result.hits.length === 0) {
    status.setText("nothing related yet");
    return;
  }

  if (deps.renderNudge) deps.renderNudge(container, result);

  const list = container.createEl("ul", { cls: "hypermnesic-related-list" });
  list.setAttribute("role", "list");
  result.hits.forEach((hit, i) => renderHit(list, hit, i, deps));
  enableRovingFocus(list);
}

function renderHit(list: HTMLElement, hit: RankedHit, index: number, deps: RenderDeps): void {
  const li = list.createEl("li", { cls: "hypermnesic-hit" });
  li.setAttribute("role", "listitem");

  const link = li.createEl("a", { text: hit.path, cls: "internal-link", href: "#" });
  link.setAttribute("tabindex", index === 0 ? "0" : "-1");
  link.setAttribute("aria-label", hit.heading ? `${hit.path}, ${hit.heading}` : hit.path);
  link.addEventListener("click", (evt) => {
    evt.preventDefault();
    deps.openNote(hit.path);
  });
  link.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter" || evt.key === " ") {
      evt.preventDefault();
      deps.openNote(hit.path);
    }
  });

  if (hit.heading) li.createSpan({ text: ` — ${hit.heading}`, cls: "hypermnesic-heading" });

  const meta = li.createSpan({ cls: "hypermnesic-hit-meta" });
  for (const channel of hit.channels) {
    const chip = meta.createSpan({
      cls: `hypermnesic-chip hypermnesic-chip-${channel}`,
      text: channel,
    });
    chip.setAttribute("title", CHANNEL_TITLE[channel] ?? channel);
  }
  const stale = stalenessLabel(hit);
  const tag = meta.createSpan({ cls: "hypermnesic-staleness", text: stale.text });
  tag.setAttribute("title", stale.title);
}

/** Roving-tabindex arrow navigation among the result links (FR-R20). */
function enableRovingFocus(list: HTMLElement): void {
  const links = Array.from(list.querySelectorAll("a")) as HTMLElement[];
  if (links.length === 0) return;
  list.addEventListener("keydown", (evt: KeyboardEvent) => {
    if (evt.key !== "ArrowDown" && evt.key !== "ArrowUp") return;
    evt.preventDefault();
    const current = links.findIndex((l) => l === document.activeElement);
    const start = current < 0 ? 0 : current;
    let next = start + (evt.key === "ArrowDown" ? 1 : -1);
    next = Math.max(0, Math.min(links.length - 1, next));
    links.forEach((l, i) => l.setAttribute("tabindex", i === next ? "0" : "-1"));
    links[next]?.focus();
  });
}
