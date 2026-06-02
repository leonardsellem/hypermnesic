/**
 * src/nudge.ts — the interrogable, view-only reinvention nudge (U40, FR-R13/14/15).
 *
 * When the top hit's similarity ≥ the threshold for the current block, show a
 * nudge that EXPANDS to the matched snippet + a one-hop build_context peek, so
 * the "you may be reinventing [[X]]" claim is checkable rather than an
 * unfalsifiable accusation. The reinvention link and the context-peek list render
 * through the shared reference-row primitive, so they get a resolved title (not
 * the literal `[[path]]`), Page-preview hover, the context menu, and insertion —
 * and a non-local target degrades to an honest muted row. The nudge is
 * dismissable/mutable PER NOTE — muting is plugin-local state (persisted via the
 * store) and never edits the note. It exposes no write affordance in v1.
 */
import { ButtonComponent, HoverParent, Notice } from "obsidian";
import { ContextResponse, CoreResult, callTool, parseToolResult } from "./core";
import { ReferenceRowDeps, renderReference, resolveReference } from "./surfaces/reference";

/** Plugin-local mute state. Implemented by the plugin over persisted data;
 *  muting never touches the vault. */
export interface NudgeStore {
  isMuted(notePath: string): boolean;
  mute(notePath: string): Promise<void>;
  unmute(notePath: string): Promise<void>;
}

export interface NudgeDeps {
  getUrl(): string;
  store: NudgeStore;
  threshold(): number;
  activePath(): string;
  /** Shared reference-row deps (resolution, navigation, hover, menu, insertion). */
  rowDeps: ReferenceRowDeps;
}

/** Whether to show the nudge for the current block. */
export function shouldNudge(
  result: CoreResult | null,
  threshold: number,
  muted: boolean,
): boolean {
  if (!result || muted) return false;
  const top = result.hits[0];
  return !!top && top.score >= threshold;
}

export function renderNudge(
  host: HTMLElement,
  result: CoreResult,
  deps: NudgeDeps,
  hoverParent: HoverParent | null,
): void {
  const activePath = deps.activePath();
  if (!shouldNudge(result, deps.threshold(), deps.store.isMuted(activePath))) return;
  const top = result.hits[0];
  const sourcePath = result.sourcePath;

  const box = host.createEl("div", { cls: "hypermnesic-nudge" });
  box.setAttribute("role", "note");

  const header = box.createEl("div", { cls: "hypermnesic-nudge-header" });
  header.createEl("strong", { text: "You may be reinventing: " });
  const refHost = header.createSpan({ cls: "hypermnesic-nudge-ref" });
  const resolved = resolveReference(
    deps.rowDeps.app,
    { path: top.path, heading: top.heading, snippet: top.snippet },
    sourcePath,
  );
  renderReference(refHost, resolved, sourcePath, deps.rowDeps, hoverParent);

  // The matched snippet makes the claim inspectable.
  if (top.snippet) {
    box.createEl("blockquote", { cls: "hypermnesic-nudge-snippet", text: top.snippet });
  }

  const actions = box.createEl("div", { cls: "hypermnesic-nudge-actions" });
  const peekOut = box.createEl("div", { cls: "hypermnesic-nudge-peek" });

  // "Check context" — a one-hop build_context peek (read-only).
  new ButtonComponent(actions).setButtonText("Check context").onClick(async () => {
    peekOut.empty();
    peekOut.setText("loading…");
    try {
      const ctx = parseToolResult<ContextResponse>(
        await callTool(deps.getUrl(), "build_context", { path: top.path, depth: 1 }),
      );
      renderPeek(peekOut, ctx, deps, sourcePath, hoverParent);
    } catch {
      peekOut.setText("could not load context");
    }
  });

  // "Mute for this note" — plugin-local, persisted, never edits the note.
  new ButtonComponent(actions).setButtonText("Mute for this note").onClick(async () => {
    await deps.store.mute(activePath);
    box.remove();
    new Notice("hypermnesic: nudge muted for this note");
  });
}

function renderPeek(
  host: HTMLElement,
  ctx: ContextResponse | null,
  deps: NudgeDeps,
  sourcePath: string,
  hoverParent: HoverParent | null,
): void {
  host.empty();
  const reachable = extractReachable(ctx?.context);
  if (reachable.length === 0) {
    host.setText("no linked context");
    return;
  }
  const ul = host.createEl("ul", { cls: "hypermnesic-nudge-context" });
  for (const path of reachable.slice(0, 8)) {
    const li = ul.createEl("li");
    const resolved = resolveReference(deps.rowDeps.app, { path }, sourcePath);
    renderReference(li, resolved, sourcePath, deps.rowDeps, hoverParent);
  }
}

/** build_context's `context` is engine-shaped; accept an array of strings /
 *  {path} objects or an adjacency object's keys. */
function extractReachable(context: unknown): string[] {
  if (Array.isArray(context)) {
    return context
      .map((c) =>
        typeof c === "string"
          ? c
          : c && typeof c === "object" && typeof (c as { path?: unknown }).path === "string"
            ? (c as { path: string }).path
            : "",
      )
      .filter((s): s is string => s.length > 0);
  }
  if (context && typeof context === "object") {
    return Object.keys(context as Record<string, unknown>);
  }
  return [];
}
