/**
 * hypermnesic companion — a strictly read-only recall surface over the tailnet
 * hypermnesic MCP. (Phase 2.5 Plan 2.)
 *
 * READ-ONLY BY CONSTRUCTION: all engine access goes through src/core.ts's
 * callTool(), which refuses any tool outside READ_ONLY_TOOLS. The plugin performs
 * NO vault writes — no modify/create/delete/append/trash calls, no adapter writes.
 * Writes belong to agents via the engine's gated commit_note tool, never here.
 *
 * The shared retrieval core (U36) fans one ranked result (U37) out to the calm
 * surfaces (U38: status-bar popover, opt-in sidebar, optional CM6 marker),
 * thinking-mode + selection-recall (U39), and the interrogable reinvention nudge
 * (U40). The trust/state machine + settings + compliance land in U41.
 */
import {
  Editor,
  ItemView,
  MarkdownFileInfo,
  MarkdownView,
  Notice,
  Plugin,
  TFile,
  WorkspaceLeaf,
  debounce,
} from "obsidian";
import { DEFAULT_SETTINGS, HypermnesicSettings } from "./src/types";
import { HypermnesicSettingTab } from "./src/settings";
import { CoreResult, RetrievalCore, extractCursorWindow } from "./src/core";
import { RecallState, RenderDeps, renderResultList } from "./src/surfaces/render";
import { StatusBarSurface } from "./src/surfaces/statusbar";
import { hypermnesicGutter } from "./src/surfaces/gutter";
import { runThinking } from "./src/thinking";
import { NudgeStore, renderNudge } from "./src/nudge";

export const SIDEBAR_VIEW_TYPE = "hypermnesic-recall";

interface PluginData {
  settings: HypermnesicSettings;
  mutedNotes: string[];
}

/** The opt-in sidebar. It renders the core's last result through the shared
 *  renderer; it issues no query of its own (KTD1). */
class RecallSidebarView extends ItemView {
  constructor(
    leaf: WorkspaceLeaf,
    private plugin: HypermnesicPlugin,
  ) {
    super(leaf);
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
    this.draw();
  }

  draw(): void {
    const root = this.containerEl.children[1] as HTMLElement;
    renderResultList(root, this.plugin.lastResult, this.plugin.lastState, this.plugin.renderDeps);
  }
}

export default class HypermnesicPlugin extends Plugin {
  settings: HypermnesicSettings = DEFAULT_SETTINGS;
  private mutedNotes = new Set<string>();

  core!: RetrievalCore;
  renderDeps!: RenderDeps;
  lastResult: CoreResult | null = null;
  lastState: RecallState = "idle";

  private statusBar: StatusBarSurface | null = null;

  async onload(): Promise<void> {
    await this.loadPersisted();

    this.core = new RetrievalCore({
      getUrl: () => this.settings.mcpUrl,
      getSettings: () => this.settings,
      mtimeFallback: (path) => this.localMtimeSeconds(path),
      now: () => Date.now() / 1000,
    });
    void this.core.probe();

    this.renderDeps = this.buildRenderDeps();

    this.registerView(SIDEBAR_VIEW_TYPE, (leaf) => new RecallSidebarView(leaf, this));

    if (this.settings.showStatusBar) this.createStatusBar();

    // Optional CM6 inline marker — registered via the supported extension path
    // (auto-cleaned on unload). Pulls from the core; never queries or mutates.
    this.registerEditorExtension(
      hypermnesicGutter({
        enabled: () => this.settings.showGutter,
        count: () => this.lastResult?.hits.length ?? 0,
      }),
    );

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
    this.addCommand({
      id: "think-about-note",
      name: "Think about this note or selection",
      callback: () => void this.thinkAbout(),
    });
    this.addCommand({
      id: "recall-about-selection",
      name: "Recall about selection",
      editorCallback: (editor, view) => void this.recallSelection(editor, view),
    });

    this.addSettingTab(new HypermnesicSettingTab(this.app, this));

    // Pause trigger: resetTimer debounce fires only after typing stops for
    // pauseMs — never per-keystroke; findings hold during sustained typing.
    const onPause = debounce(() => void this.triggerRecall(), this.settings.pauseMs, true);
    this.registerEvent(this.app.workspace.on("editor-change", () => onPause()));
  }

  onunload(): void {
    // Intentionally no leaf detaching on unload: Obsidian tears down registered
    // views itself and preserves leaf placement across plugin updates. (Detaching
    // leaves here was the prior guideline violation this redesign removed.)
  }

  // ───────────────────────────── pipeline + surfaces ────────────────────────

  /** The core trigger: extract the cursor window and run one query. */
  async triggerRecall(): Promise<void> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (!view) return;
    const windowText = extractCursorWindow(view.editor);
    const activePath = view.file?.path ?? "";

    this.pushToSurfaces(this.lastResult, "loading");
    try {
      const result = await this.core.run(windowText, activePath);
      this.lastResult = result;
      this.pushToSurfaces(result, this.deriveState(result));
    } catch {
      this.pushToSurfaces(this.lastResult, "offline");
    }
  }

  /** Selection-as-query recall (FR-R16): send the highlighted text to search. */
  async recallSelection(editor: Editor, ctx: MarkdownView | MarkdownFileInfo): Promise<void> {
    const selection = editor.getSelection().trim();
    if (!selection) {
      new Notice("hypermnesic: select some text to recall about");
      return;
    }
    await this.activateSidebar();
    this.pushToSurfaces(this.lastResult, "loading");
    try {
      const result = await this.core.run(selection, ctx.file?.path ?? "");
      this.lastResult = result;
      this.pushToSurfaces(result, this.deriveState(result));
    } catch {
      this.pushToSurfaces(this.lastResult, "offline");
    }
  }

  /** Thinking-mode (FR-R10/11): selection, else cursor window, else note title. */
  async thinkAbout(): Promise<void> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (!view) {
      new Notice("hypermnesic: open a note to think about");
      return;
    }
    const selection = view.editor.getSelection().trim();
    const topic = selection || extractCursorWindow(view.editor) || view.file?.basename || "";
    await runThinking(this.app, this.settings.mcpUrl, topic, this.core.capabilities.hasThink);
  }

  private deriveState(result: CoreResult | null): RecallState {
    if (!result) return "empty";
    if (result.manualReindex) return "reindex";
    if (result.degraded) return "degraded";
    return result.hits.length > 0 ? "results" : "empty";
  }

  /** Fan the one result out to every surface (KTD1). */
  private pushToSurfaces(result: CoreResult | null, state: RecallState): void {
    this.lastResult = result;
    this.lastState = state;
    this.statusBar?.update(result, state);
    for (const leaf of this.app.workspace.getLeavesOfType(SIDEBAR_VIEW_TYPE)) {
      const view = leaf.view;
      if (view instanceof RecallSidebarView) view.draw();
    }
  }

  private buildRenderDeps(): RenderDeps {
    return {
      app: this.app,
      openNote: (path) => this.app.workspace.openLinkText(path, "", false),
      renderNudge: (host, result) =>
        renderNudge(host, result, {
          app: this.app,
          getUrl: () => this.settings.mcpUrl,
          store: this.nudgeStore(),
          threshold: () => this.settings.reinventThreshold,
          activePath: () => this.app.workspace.getActiveViewOfType(MarkdownView)?.file?.path ?? "",
          openNote: (path) => this.app.workspace.openLinkText(path, "", false),
        }),
    };
  }

  private createStatusBar(): void {
    const el = this.addStatusBarItem();
    this.statusBar = new StatusBarSurface(el, this.renderDeps);
    this.statusBar.update(this.lastResult, this.lastState);
    // Remove the body-appended popover on unload (auto-cleanup).
    this.register(() => this.statusBar?.dispose());
  }

  /** Settings-tab hook: re-probe capabilities after a URL change. */
  onSettingsChanged(): void {
    void this.core.probe();
  }

  // ───────────────────────────── nudge mute (plugin-local) ──────────────────

  private nudgeStore(): NudgeStore {
    return {
      isMuted: (notePath) => this.mutedNotes.has(notePath),
      mute: async (notePath) => {
        this.mutedNotes.add(notePath);
        await this.persist();
      },
      unmute: async (notePath) => {
        this.mutedNotes.delete(notePath);
        await this.persist();
      },
    };
  }

  // ───────────────────────────── helpers + persistence ──────────────────────

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

  async loadPersisted(): Promise<void> {
    const raw = (await this.loadData()) as Partial<PluginData> | HypermnesicSettings | null;
    // Back-compat: older builds stored the settings object at the top level.
    const stored =
      raw && typeof raw === "object" && "settings" in raw
        ? (raw as PluginData).settings
        : (raw as Partial<HypermnesicSettings> | null);
    this.settings = Object.assign({}, DEFAULT_SETTINGS, stored ?? {});
    const muted = raw && typeof raw === "object" && "mutedNotes" in raw ? (raw as PluginData).mutedNotes : [];
    this.mutedNotes = new Set(muted ?? []);
  }

  private async persist(): Promise<void> {
    const data: PluginData = { settings: this.settings, mutedNotes: Array.from(this.mutedNotes) };
    await this.saveData(data);
  }

  async saveSettings(): Promise<void> {
    await this.persist();
  }
}
