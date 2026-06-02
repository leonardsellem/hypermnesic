/**
 * hypermnesic companion — a strictly read-only recall surface over the tailnet
 * hypermnesic MCP. (Phase 2.5 Plan 2.)
 *
 * READ-ONLY BY CONSTRUCTION: all engine access goes through src/core.ts's
 * callTool(), which refuses any tool outside READ_ONLY_TOOLS. The plugin performs
 * NO vault writes — no modify/create/delete/append/trash calls, no adapter writes.
 * Writes belong to agents via the engine's gated commit_note tool, never here.
 *
 * U36 wires the shared retrieval core: a pause trigger (idle past the configured
 * interval, or an explicit command) extracts the cursor window, the core queries
 * once and caches, and every surface renders that one ranked result (KTD1).
 */
import {
  Editor,
  ItemView,
  MarkdownView,
  Plugin,
  TFile,
  WorkspaceLeaf,
  debounce,
} from "obsidian";
import { DEFAULT_SETTINGS, HypermnesicSettings } from "./src/types";
import { HypermnesicSettingTab } from "./src/settings";
import { CoreResult, RetrievalCore, extractCursorWindow } from "./src/core";
import type { RankedHit } from "./src/ranking";

export const SIDEBAR_VIEW_TYPE = "hypermnesic-recall";

type SurfaceState = "idle" | "loading" | "results" | "offline" | "empty";

/** The opt-in sidebar. It renders the core's last result; it issues no query of
 *  its own (KTD1). Phase C extracts this into a shared renderer with the popover. */
class RecallSidebarView extends ItemView {
  plugin: HypermnesicPlugin;

  constructor(leaf: WorkspaceLeaf, plugin: HypermnesicPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return SIDEBAR_VIEW_TYPE;
  }
  getDisplayText(): string {
    return "hypermnesic — recall";
  }
  getIcon(): string {
    return "links-coming-in";
  }

  async onOpen(): Promise<void> {
    this.renderResult(this.plugin.lastResult, this.plugin.lastResult ? "results" : "idle");
  }

  /** Pure DOM render of a ranked result. No writes; navigation opens existing
   *  notes only. */
  renderResult(result: CoreResult | null, state: SurfaceState): void {
    const root = this.containerEl.children[1];
    root.empty();
    root.createEl("h4", { text: "Related notes" });

    if (state === "loading") {
      root.createEl("div", { text: "thinking…", cls: "hypermnesic-status" });
      return;
    }
    if (state === "offline") {
      root.createEl("div", {
        text: "offline — could not reach the tailnet index",
        cls: "hypermnesic-status",
      });
      return;
    }
    if (!result || result.hits.length === 0) {
      root.createEl("div", { text: "nothing related yet", cls: "hypermnesic-status" });
      return;
    }

    const list = root.createEl("ul", { cls: "hypermnesic-related-list" });
    for (const hit of result.hits) {
      this.renderHit(list, hit);
    }
  }

  private renderHit(list: HTMLElement, hit: RankedHit): void {
    const li = list.createEl("li", { cls: "hypermnesic-hit" });
    const link = li.createEl("a", { text: hit.path, cls: "internal-link" });
    link.addEventListener("click", (evt) => {
      evt.preventDefault();
      // Read-only navigation: open the existing note, never create one.
      this.plugin.app.workspace.openLinkText(hit.path, "", false);
    });
    if (hit.heading) li.createSpan({ text: ` — ${hit.heading}` });
    if (hit.channels.length) {
      li.createSpan({ text: ` [${hit.channels.join("·")}]`, cls: "hypermnesic-channels" });
    }
  }
}

export default class HypermnesicPlugin extends Plugin {
  settings: HypermnesicSettings = DEFAULT_SETTINGS;
  core!: RetrievalCore;
  lastResult: CoreResult | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.core = new RetrievalCore({
      getUrl: () => this.settings.mcpUrl,
      getSettings: () => this.settings,
      mtimeFallback: (path) => this.localMtimeSeconds(path),
      now: () => Date.now() / 1000,
    });
    // Capability handshake — non-blocking; surfaces degrade until it resolves.
    void this.core.probe();

    this.registerView(SIDEBAR_VIEW_TYPE, (leaf) => new RecallSidebarView(leaf, this));

    this.addCommand({
      id: "open-recall-sidebar",
      name: "Open recall sidebar",
      callback: () => void this.activateSidebar(),
    });
    this.addCommand({
      id: "recall-related-now",
      name: "Recall related notes now",
      callback: () => void this.triggerRecall(),
    });

    this.addSettingTab(new HypermnesicSettingTab(this.app, this));

    // Pause trigger: debounce with resetTimer=true fires only after typing stops
    // for pauseMs — never per-keystroke, and findings hold during sustained
    // typing (FR-R3/R7).
    const onPause = debounce(() => void this.triggerRecall(), this.settings.pauseMs, true);
    this.registerEvent(this.app.workspace.on("editor-change", () => onPause()));
  }

  onunload(): void {
    // Intentionally no leaf detaching on unload: Obsidian tears down registered
    // views itself and preserves leaf placement across plugin updates. (Detaching
    // leaves here was the prior guideline violation this redesign removed.)
  }

  /** The core pipeline trigger: extract the cursor window and run one query. */
  async triggerRecall(): Promise<void> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (!view) return;
    const editor: Editor = view.editor;
    const windowText = extractCursorWindow(editor);
    const activePath = view.file?.path ?? "";

    this.pushToSurfaces(this.lastResult, "loading");
    try {
      const result = await this.core.run(windowText, activePath);
      this.lastResult = result;
      this.pushToSurfaces(result, result && result.hits.length ? "results" : "empty");
    } catch {
      this.pushToSurfaces(this.lastResult, "offline");
    }
  }

  /** Fan the one result out to every open surface (KTD1). Phase C adds the
   *  status-bar/gutter; today it is the opt-in sidebar. */
  private pushToSurfaces(result: CoreResult | null, state: SurfaceState): void {
    for (const leaf of this.app.workspace.getLeavesOfType(SIDEBAR_VIEW_TYPE)) {
      const view = leaf.view;
      if (view instanceof RecallSidebarView) view.renderResult(result, state);
    }
  }

  /** Local mtime (epoch seconds) for a vault path, or null. A read-only stat —
   *  the forgetting-curve fallback when the engine recency is absent. */
  localMtimeSeconds(path: string): number | null {
    const file = this.app.vault.getAbstractFileByPath(path);
    return file instanceof TFile ? file.stat.mtime / 1000 : null;
  }

  /** Reveal the recall sidebar, reusing an existing leaf if one is open. */
  async activateSidebar(): Promise<void> {
    const existing = this.app.workspace.getLeavesOfType(SIDEBAR_VIEW_TYPE);
    if (existing.length > 0) {
      this.app.workspace.revealLeaf(existing[0]);
      return;
    }
    const leaf = this.app.workspace.getRightLeaf(false);
    if (leaf) {
      await leaf.setViewState({ type: SIDEBAR_VIEW_TYPE, active: true });
      this.app.workspace.revealLeaf(leaf);
    }
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }
  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }
}
