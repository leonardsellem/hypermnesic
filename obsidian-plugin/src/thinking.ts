/**
 * src/thinking.ts — in-editor thinking-mode (U39, FR-R10/R11/R12).
 *
 * "Think about this note/selection" calls the engine's read-only `think` tool and
 * renders related / questions / tensions with a visible `wrote: false` proof
 * badge and NO write affordance. Degrades gracefully when `think` is not served
 * by the connected engine (capability handshake). Read-only throughout.
 */
import { App, Modal, Notice } from "obsidian";
import { ThinkResponse, callTool, parseToolResult } from "./core";

function relatedLabel(related: Record<string, unknown>): string {
  const path = typeof related.path === "string" ? related.path : "";
  const heading = typeof related.heading === "string" ? related.heading : "";
  if (path && heading) return `${path} — ${heading}`;
  return path || JSON.stringify(related);
}

class ThinkingModal extends Modal {
  constructor(
    app: App,
    private topic: string,
    private resp: ThinkResponse,
  ) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("hypermnesic-thinking");
    contentEl.createEl("h3", { text: `Thinking about: ${this.topic}` });

    // The observable no-write assertion — a visible proof badge (FR-R11).
    const badge = contentEl.createEl("div", { cls: "hypermnesic-wrote-badge" });
    badge.setText(this.resp.wrote === false ? "✓ read-only · wrote: false" : "⚠ unexpected write flag");
    badge.setAttribute("aria-label", "this thinking surface made no writes");

    this.section(contentEl, "Related", (this.resp.related ?? []).map(relatedLabel));
    this.section(contentEl, "Questions", this.resp.questions ?? []);
    this.section(contentEl, "Tensions", this.resp.tensions ?? []);

    const empty =
      !(this.resp.related ?? []).length &&
      !(this.resp.questions ?? []).length &&
      !(this.resp.tensions ?? []).length;
    if (empty) {
      contentEl.createEl("p", {
        text: "nothing relevant yet — the index has no close match",
        cls: "hypermnesic-status",
      });
    }
  }

  private section(host: HTMLElement, title: string, items: string[]): void {
    if (!items.length) return;
    host.createEl("h4", { text: title });
    const ul = host.createEl("ul");
    for (const item of items) ul.createEl("li", { text: item });
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

/**
 * Run thinking-mode for a topic and open the read-only modal. No write affordance
 * is ever presented. Degrades to a Notice when `think` is unavailable or the
 * endpoint is unreachable.
 */
export async function runThinking(
  app: App,
  url: string,
  topic: string,
  hasThink: boolean,
): Promise<void> {
  if (!topic.trim()) {
    new Notice("hypermnesic: nothing to think about (empty selection/note)");
    return;
  }
  if (!hasThink) {
    new Notice("hypermnesic: thinking-mode unavailable on this engine");
    return;
  }
  let resp: ThinkResponse | null;
  try {
    resp = parseToolResult<ThinkResponse>(await callTool(url, "think", { topic }));
  } catch {
    new Notice("hypermnesic: could not reach the tailnet index");
    return;
  }
  if (!resp) {
    new Notice("hypermnesic: no response from thinking-mode");
    return;
  }
  new ThinkingModal(app, topic, resp).open();
}
