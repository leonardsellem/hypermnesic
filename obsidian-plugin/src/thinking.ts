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
  Notice,
  WorkspaceLeaf,
  setIcon,
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

/** Bound the think-deeper history so a long chain can't grow memory unbounded;
 *  at the cap, "think deeper" is disabled so "back" always reaches the origin. */
const MAX_THINK_DEPTH = 10;

/** A cached frame on the think-deeper history stack — engine data only, so each
 *  render re-resolves references against the live vault (KTD6). */
interface ThinkingFrame {
  topic: string;
  sourcePath: string;
  state: ThinkingState;
  response: ThinkResponse | null;
}

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
  /** Prior frames for the think-deeper back affordance (KTD6). */
  private stack: ThinkingFrame[] = [];

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

  /** Closing the leaf clears the chain so a re-opened panel starts fresh, never
   *  resurrecting a stale back-stack (KTD6). */
  async onClose(): Promise<void> {
    this.stack = [];
    this.response = null;
    this.state = "idle";
    this.topic = "";
  }

  /** Push the current frame and think about a related note in place (R11). */
  private async deepen(topic: string, sourcePath: string): Promise<void> {
    if (this.stack.length >= MAX_THINK_DEPTH) {
      new Notice("hypermnesic: thinking depth limit reached");
      return;
    }
    this.stack.push({
      topic: this.topic,
      sourcePath: this.sourcePath,
      state: this.state,
      response: this.response,
    });
    await this.loadTopic(topic, sourcePath);
  }

  /** Pop to the cached prior frame; render re-resolves its references (KTD6). */
  private goBack(): void {
    const prev = this.stack.pop();
    if (!prev) return;
    this.topic = prev.topic;
    this.sourcePath = prev.sourcePath;
    this.state = prev.state;
    this.response = prev.response;
    this.render();
  }

  /** Fresh entry point (the command / menu): start a new chain. `sourcePath` is
   *  the note the topic came from — it keeps reference resolution stable as the
   *  panel survives navigation (R8). */
  async setTopic(topic: string, sourcePath: string): Promise<void> {
    this.stack = [];
    await this.loadTopic(topic, sourcePath);
  }

  private async loadTopic(topic: string, sourcePath: string): Promise<void> {
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

    if (this.stack.length > 0) this.renderNav(root);

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

  /** Back control + topic breadcrumb, shown while a think-deeper chain is open. */
  private renderNav(root: HTMLElement): void {
    const nav = root.createDiv({ cls: "hypermnesic-think-nav" });
    const back = nav.createEl("button", { cls: "hypermnesic-back" });
    back.setAttribute("aria-label", "Back to the previous thinking result");
    setIcon(back, "arrow-left");
    back.createSpan({ text: "Back" });
    back.addEventListener("click", () => this.goBack());

    const crumbs = nav.createSpan({ cls: "hypermnesic-breadcrumb" });
    crumbs.setAttribute("aria-hidden", "true");
    const trail = [...this.stack.map((f) => f.topic), this.topic];
    trail.forEach((label, i) => {
      if (i > 0) crumbs.createSpan({ cls: "hypermnesic-crumb-sep", text: " › " });
      crumbs.createSpan({ cls: "hypermnesic-crumb", text: label });
    });
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
      // Guard the rendered links even if render rejects, so a partial render can
      // never leave an un-neutralized create-on-click link (R28 hardening).
      void MarkdownRenderer.render(this.deps.rowDeps.app, item, li, this.sourcePath, this)
        .then(() => this.guardProseLinks(li))
        .catch(() => this.guardProseLinks(li));
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
    const atCap = this.stack.length >= MAX_THINK_DEPTH;
    for (const item of related) {
      const li = list.createEl("li", { cls: "hypermnesic-hit" });
      li.setAttribute("role", "listitem");
      const resolved = resolveReference(this.deps.rowDeps.app, toReferenceInput(item), this.sourcePath);
      focusables.push(renderReference(li, resolved, this.sourcePath, this.deps.rowDeps, this));

      // Inline "think deeper" — re-runs `think` on this note in place (R11).
      const deepen = li.createEl("button", { cls: "hypermnesic-deepen" });
      setIcon(deepen, "brain");
      if (atCap) {
        deepen.setAttribute("disabled", "true");
        deepen.setAttribute("aria-label", "Think deeper (depth limit reached)");
      } else {
        deepen.setAttribute("aria-label", `Think deeper about ${resolved.display.title}`);
        deepen.addEventListener("click", () =>
          void this.deepen(resolved.display.title, resolved.file?.path ?? this.sourcePath),
        );
      }
    }
    enableRovingFocus(list, focusables);
  }
}
