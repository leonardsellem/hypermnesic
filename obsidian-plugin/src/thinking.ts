/**
 * src/thinking.ts — in-editor thinking-mode as a dockable panel (U39 + first-class
 * redesign, FR-R10/R11/R12).
 *
 * "Think about this note/selection" calls the engine's read-only `think` tool and
 * renders related / questions / tensions in a persistent, dockable ItemView (like
 * Backlinks/Outline) — not a dead-end modal. Related notes render through the
 * shared reference-row primitive (navigable links + Page-preview hover + menu +
 * insertion); Questions and Tensions render as markdown so embedded wikilinks are
 * live, with unresolved links neutralized so they never create a note (R28). A
 * visible `wrote: false` proof badge and the trust badge ride every render; there
 * is NO write affordance. Read-only throughout.
 */
import {
  HoverPopover,
  ItemView,
  MarkdownRenderer,
  WorkspaceLeaf,
} from "obsidian";
import { ThinkResponse, callTool, parseToolResult } from "./core";
import { renderTrustBadge } from "./state";
import {
  ReferenceRowDeps,
  enableRovingFocus,
  linkResolvesLocally,
  renderReference,
  resolveReference,
} from "./surfaces/reference";
import { ReferenceInput } from "./surfaces/reference-model";

export const THINKING_VIEW_TYPE = "hypermnesic-thinking";

export interface ThinkingDeps {
  getUrl(): string;
  hasThink(): boolean;
  /** Shared reference-row deps (resolution, navigation, hover, menu, insertion). */
  rowDeps: ReferenceRowDeps;
}

type ThinkingState = "idle" | "loading" | "ready" | "unavailable" | "unreachable";

/** Adapt an engine `related` item (path / heading / neither) into the shared
 *  reference shape. An item with no usable path renders as a non-local row
 *  rather than crashing the renderer. */
function toReferenceInput(related: Record<string, unknown>): ReferenceInput {
  const path = typeof related.path === "string" ? related.path : "";
  const heading = typeof related.heading === "string" ? related.heading : undefined;
  const snippet = typeof related.snippet === "string" ? related.snippet : undefined;
  if (path) return { path, heading, snippet };
  return { path: heading ?? "(unresolved related item)", snippet };
}

export class ThinkingView extends ItemView {
  // Satisfy HoverParent so reference rows in this panel get native Page-preview.
  hoverPopover: HoverPopover | null = null;

  private topic = "";
  private sourcePath = "";
  private state: ThinkingState = "idle";
  private response: ThinkResponse | null = null;

  constructor(
    leaf: WorkspaceLeaf,
    private deps: ThinkingDeps,
  ) {
    super(leaf);
  }

  getViewType(): string {
    return THINKING_VIEW_TYPE;
  }
  getDisplayText(): string {
    return "hypermnesic — thinking";
  }
  getIcon(): string {
    return "brain";
  }

  async onOpen(): Promise<void> {
    this.render();
  }

  /** Run thinking-mode for a topic and render in place (R8: one panel, refreshed).
   *  `sourcePath` is the note the topic came from — it keeps reference resolution
   *  stable as the panel survives navigation. */
  async setTopic(topic: string, sourcePath: string): Promise<void> {
    this.topic = topic;
    this.sourcePath = sourcePath;

    if (!this.deps.hasThink()) {
      this.state = "unavailable";
      this.response = null;
      this.render();
      return;
    }

    this.state = "loading";
    this.response = null;
    this.render();

    try {
      this.response = parseToolResult<ThinkResponse>(
        await callTool(this.deps.getUrl(), "think", { topic }),
      );
      this.state = "ready";
    } catch {
      this.response = null;
      this.state = "unreachable";
    }
    this.render();
  }

  private get body(): HTMLElement {
    return this.containerEl.children[1] as HTMLElement;
  }

  private render(): void {
    const root = this.body;
    root.empty();
    root.addClass("hypermnesic-thinking");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "hypermnesic thinking");

    renderTrustBadge(root);

    // The observable no-write assertion — a visible proof badge (FR-R11/R10).
    const wrote = this.response?.wrote;
    const badge = root.createEl("div", { cls: "hypermnesic-wrote-badge" });
    badge.setText(
      wrote === false
        ? "✓ read-only · wrote: false"
        : this.response
          ? "⚠ unexpected write flag"
          : "read-only",
    );
    badge.setAttribute("aria-label", "this thinking surface made no writes");

    if (this.topic) {
      root.createEl("h3", { cls: "hypermnesic-thinking-topic", text: this.topic });
    }

    const banner = root.createEl("div", { cls: "hypermnesic-status" });
    banner.setAttribute("aria-live", "polite");

    switch (this.state) {
      case "idle":
        banner.setText("Run “Think about this note or selection” to begin.");
        return;
      case "loading":
        banner.setText("thinking…");
        return;
      case "unavailable":
        banner.setText("thinking-mode unavailable on this engine");
        return;
      case "unreachable":
        banner.setText("could not reach the tailnet index");
        return;
    }

    const resp = this.response;
    if (!resp) {
      banner.setText("no response from thinking-mode");
      return;
    }
    if (resp.degraded) banner.setText("lexical-only — the semantic channel is down");

    const related = resp.related ?? [];
    const questions = resp.questions ?? [];
    const tensions = resp.tensions ?? [];
    if (!related.length && !questions.length && !tensions.length) {
      banner.setText("nothing relevant yet — the index has no close match");
      return;
    }

    // Questions first frames the Socratic loop; Related is the navigable middle;
    // Tensions close. Zero-item sections are hidden.
    this.renderProseSection(root, "Questions", questions, "hypermnesic-thinking-questions");
    this.renderRelatedSection(root, related);
    this.renderProseSection(root, "Tensions", tensions, "hypermnesic-thinking-tensions");
  }

  private sectionHeader(host: HTMLElement, title: string, count: number): void {
    const h = host.createEl("h4", { cls: "hypermnesic-think-heading", text: title });
    h.createSpan({ cls: "hypermnesic-count", text: String(count) });
  }

  private renderProseSection(
    root: HTMLElement,
    title: string,
    items: string[],
    sectionCls: string,
  ): void {
    if (!items.length) return;
    const sec = root.createDiv({ cls: `hypermnesic-think-section ${sectionCls}` });
    this.sectionHeader(sec, title, items.length);
    const list = sec.createEl("ul", { cls: "hypermnesic-prose-list" });
    for (const item of items) {
      const li = list.createEl("li");
      void MarkdownRenderer.render(this.deps.rowDeps.app, item, li, this.sourcePath, this).then(() =>
        this.guardProseLinks(li),
      );
    }
  }

  /** Neutralize MarkdownRenderer-emitted links that don't resolve locally so a
   *  click never creates a note (R28, AE9). Resolvable links keep native
   *  navigation/preview and open the existing note. */
  private guardProseLinks(container: HTMLElement): void {
    container.querySelectorAll("a.internal-link").forEach((node) => {
      const el = node as HTMLElement;
      const href = el.getAttribute("data-href") ?? el.getAttribute("href") ?? "";
      if (href && linkResolvesLocally(this.deps.rowDeps.app, href, this.sourcePath)) return;
      el.removeClass("internal-link");
      el.addClass("hypermnesic-link-unresolved");
      el.removeAttribute("href");
      el.setAttribute("aria-disabled", "true");
      el.setAttribute("title", "not in this vault");
      el.addEventListener("click", (evt) => {
        evt.preventDefault();
        evt.stopPropagation();
      });
    });
  }

  private renderRelatedSection(root: HTMLElement, related: Array<Record<string, unknown>>): void {
    if (!related.length) return;
    const sec = root.createDiv({ cls: "hypermnesic-think-section hypermnesic-thinking-related" });
    this.sectionHeader(sec, "Related", related.length);
    const list = sec.createEl("ul", { cls: "hypermnesic-related-list" });
    list.setAttribute("role", "list");
    const focusables: HTMLElement[] = [];
    for (const item of related) {
      const li = list.createEl("li", { cls: "hypermnesic-hit" });
      li.setAttribute("role", "listitem");
      const resolved = resolveReference(this.deps.rowDeps.app, toReferenceInput(item), this.sourcePath);
      focusables.push(renderReference(li, resolved, this.sourcePath, this.deps.rowDeps, this));
    }
    enableRovingFocus(list, focusables);
  }
}
