/**
 * src/surfaces/statusbar.ts — the calm-primary surface (U38/KTD2).
 *
 * A low-footprint status-bar item showing the related-count; clicking (or
 * Enter/Space) expands a popover that renders the shared result list. Desktop
 * only (the status bar is unsupported on mobile — consistent with isDesktopOnly).
 * Read-only: it renders the core's one snapshot and issues no query of its own.
 */
import { setIcon } from "obsidian";
import { RenderDeps, renderResultList } from "./render";
import { StateSnapshot } from "../state";

export class StatusBarSurface {
  private popover: HTMLElement | null = null;
  private model: StateSnapshot;

  constructor(
    private el: HTMLElement, // from plugin.addStatusBarItem()
    private deps: RenderDeps,
    initial: StateSnapshot,
  ) {
    this.model = initial;
    this.el.addClass("hypermnesic-statusbar");
    this.el.setAttribute("role", "button");
    this.el.setAttribute("tabindex", "0");
    this.el.addEventListener("click", () => this.toggle());
    this.el.addEventListener("keydown", (evt: KeyboardEvent) => {
      if (evt.key === "Enter" || evt.key === " ") {
        evt.preventDefault();
        this.toggle();
      } else if (evt.key === "Escape") {
        this.close();
      }
    });
    this.renderIndicator();
  }

  update(model: StateSnapshot): void {
    this.model = model;
    this.renderIndicator();
    if (this.popover) this.renderPopover();
  }

  private get count(): number {
    return this.model.result?.hits.length ?? 0;
  }

  private renderIndicator(): void {
    this.el.empty();
    const icon = this.el.createSpan({ cls: "hypermnesic-statusbar-icon" });
    setIcon(icon, this.model.state === "loading" ? "loader" : "links-coming-in");
    const label =
      this.model.state === "loading"
        ? "…"
        : this.model.state === "offline" || this.model.state === "error"
          ? "—"
          : String(this.count);
    this.el.createSpan({ text: ` ${label}`, cls: "hypermnesic-statusbar-count" });
    this.el.setAttribute("aria-label", `hypermnesic — ${this.count} related notes`);
  }

  private toggle(): void {
    if (this.popover) this.close();
    else this.open();
  }

  private open(): void {
    this.popover = document.body.createDiv({ cls: "hypermnesic-popover" });
    this.popover.setAttribute("role", "dialog");
    this.popover.setAttribute("aria-label", "hypermnesic related notes");
    this.position();
    this.renderPopover();
    // Defer so the opening click does not immediately close it.
    window.setTimeout(() => document.addEventListener("click", this.onOutside, true), 0);
  }

  private onOutside = (evt: MouseEvent): void => {
    if (!this.popover) return;
    const target = evt.target as Node;
    if (this.popover.contains(target) || this.el.contains(target)) return;
    this.close();
  };

  private close(): void {
    document.removeEventListener("click", this.onOutside, true);
    this.popover?.remove();
    this.popover = null;
  }

  private position(): void {
    if (!this.popover) return;
    const rect = this.el.getBoundingClientRect();
    this.popover.style.position = "fixed";
    this.popover.style.bottom = `${window.innerHeight - rect.top + 6}px`;
    this.popover.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
    this.popover.style.maxHeight = "50vh";
    this.popover.style.overflowY = "auto";
  }

  private renderPopover(): void {
    // The popover is a body-appended element with no HoverParent leaf, so native
    // Page-preview is best-effort here (KTD4); rows fall back to the snippet peek.
    if (this.popover) renderResultList(this.popover, this.model, this.deps, null);
  }

  /** Remove the body-appended popover. Registered for auto-cleanup on unload. */
  dispose(): void {
    this.close();
  }
}
