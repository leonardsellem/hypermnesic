/**
 * hypermnesic companion — a strictly read-only recall surface over the tailnet
 * hypermnesic MCP. (Phase 2.5 Plan 2.)
 *
 * READ-ONLY BY CONSTRUCTION: all engine access goes through src/core.ts's
 * callTool(), which refuses any tool outside READ_ONLY_TOOLS. The plugin performs
 * NO vault writes — no modify/create/delete/append/trash calls, no adapter writes.
 * Writes belong to agents via the engine's gated commit_note tool, never here.
 *
 * Phase A: build scaffolding + lifecycle hygiene. The retrieval core, calm
 * surfaces, thinking-mode, nudge, and trust/state machine land in U36–U41.
 */
import { ItemView, Plugin, WorkspaceLeaf } from "obsidian";
import { DEFAULT_SETTINGS, HypermnesicSettings } from "./src/types";
import { HypermnesicSettingTab } from "./src/settings";

export const SIDEBAR_VIEW_TYPE = "hypermnesic-recall";

/** The opt-in sidebar. Phase C swaps its body for the shared result renderer. */
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
    const root = this.containerEl.children[1];
    root.empty();
    root.createEl("div", { text: "hypermnesic recall", cls: "hypermnesic-status" });
  }
}

export default class HypermnesicPlugin extends Plugin {
  settings: HypermnesicSettings = DEFAULT_SETTINGS;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.registerView(SIDEBAR_VIEW_TYPE, (leaf) => new RecallSidebarView(leaf, this));

    this.addCommand({
      id: "open-recall-sidebar",
      name: "Open recall sidebar",
      callback: () => void this.activateSidebar(),
    });

    this.addSettingTab(new HypermnesicSettingTab(this.app, this));
  }

  onunload(): void {
    // Intentionally no leaf detaching on unload: Obsidian tears down registered
    // views itself and preserves leaf placement across plugin updates. (Detaching
    // leaves here was the prior guideline violation this redesign removed.)
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
