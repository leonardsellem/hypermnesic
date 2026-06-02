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
 * surfaces (U38), thinking-mode + selection-recall (U39), and the interrogable
 * reinvention nudge (U40). One interaction-state machine + the trust layer,
 * accessibility, settings, and Obsidian compliance are U41.
 */
import {
  Editor,
  HoverPopover,
  ItemView,
  MarkdownFileInfo,
  MarkdownView,
  Menu,
  Notice,
  Plugin,
  TFile,
  WorkspaceLeaf,
  debounce,
} from "obsidian";
import { DEFAULT_SETTINGS, HypermnesicSettings } from "./src/types";
import { HypermnesicSettingTab } from "./src/settings";
import { RetrievalCore, extractCursorWindow } from "./src/core";
import { RecallStateMachine, StateSnapshot } from "./src/state";
import { RenderDeps, renderResultList } from "./src/surfaces/render";
import { ResolvedReference, localLinkText } from "./src/surfaces/reference";
import { StatusBarSurface } from "./src/surfaces/statusbar";
import { hypermnesicGutter } from "./src/surfaces/gutter";
import { THINKING_VIEW_TYPE, ThinkingDeps, ThinkingView } from "./src/thinking";
import { NudgeStore, renderNudge } from "./src/nudge";

export const SIDEBAR_VIEW_TYPE = "hypermnesic-recall";

interface PluginData {
  settings: HypermnesicSettings;
  mutedNotes: string[];
}

/** The opt-in sidebar. It renders the core's last snapshot through the shared
 *  renderer; it issues no query of its own (KTD1). */
class RecallSidebarView extends ItemView {
  // Satisfy HoverParent so the shared renderer can anchor native Page-preview
  // popovers to this leaf (KTD4).
  hoverPopover: HoverPopover | null = null;

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
    renderResultList(root, this.plugin.snapshot, this.plugin.renderDeps, this);
  }
}

export default class HypermnesicPlugin extends Plugin {
  settings: HypermnesicSettings = DEFAULT_SETTINGS;
  private mutedNotes = new Set<string>();

  core!: RetrievalCore;
  renderDeps!: RenderDeps;
  private machine = new RecallStateMachine();
  snapshot: StateSnapshot = this.machine.snapshot;

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
    this.registerView(THINKING_VIEW_TYPE, (leaf) => new ThinkingView(leaf, this.buildThinkingDeps()));

    // Register as a Page-preview emitter so reference rows get native hover
    // previews integrated with the core plugin + the user's modifier preference.
    this.registerHoverLinkSource("hypermnesic-companion", {
      display: "hypermnesic",
      defaultMod: true,
    });

    if (this.settings.showStatusBar) this.createStatusBar();

    // Optional CM6 inline marker — registered via the supported extension path
    // (auto-cleaned on unload). Pulls from the core; never queries or mutates.
    this.registerEditorExtension(
      hypermnesicGutter({
        enabled: () => this.settings.showGutter,
        count: () => this.snapshot.result?.hits.length ?? 0,
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
      editorCallback: (editor, ctx) => void this.recallSelection(editor, ctx),
    });

    this.addSettingTab(new HypermnesicSettingTab(this.app, this));

    // OAuth seam (DEP-R18): future MCP OAuth attaches here via
    // registerObsidianProtocolHandler + PKCE. Intentionally NOT implemented now —
    // the tailnet membership is the boundary, and no credential is read or logged.

    // Pause trigger: resetTimer debounce fires only after typing stops for
    // pauseMs — never per-keystroke; findings hold during sustained typing.
    const onPause = debounce(() => void this.triggerRecall(), this.settings.pauseMs, true);
    this.registerEvent(this.app.workspace.on("editor-change", () => onPause()));

    if (this.settings.openSidebarOnLoad) {
      this.app.workspace.onLayoutReady(() => void this.activateSidebar());
    }
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

    this.applySnapshot(this.machine.loading());
    try {
      const result = await this.core.run(windowText, activePath);
      this.applySnapshot(this.machine.success(result));
    } catch {
      this.applySnapshot(this.machine.failure("offline"));
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
    this.applySnapshot(this.machine.loading());
    try {
      const result = await this.core.run(selection, ctx.file?.path ?? "");
      this.applySnapshot(this.machine.success(result));
    } catch {
      this.applySnapshot(this.machine.failure("offline"));
    }
  }

  /** Thinking-mode (FR-R10/11): selection, else cursor window, else note title.
   *  Opens the dockable thinking panel and renders in place. */
  async thinkAbout(): Promise<void> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (!view) {
      new Notice("hypermnesic: open a note to think about");
      return;
    }
    const selection = view.editor.getSelection().trim();
    const topic = selection || extractCursorWindow(view.editor) || view.file?.basename || "";
    if (!topic.trim()) {
      new Notice("hypermnesic: nothing to think about (empty selection/note)");
      return;
    }
    await this.runThinkingInPanel(topic, view.file?.path ?? "");
  }

  private buildThinkingDeps(): ThinkingDeps {
    return {
      getUrl: () => this.settings.mcpUrl,
      hasThink: () => this.core.capabilities.hasThink,
      rowDeps: this.renderDeps,
    };
  }

  /** Reveal the dockable thinking panel, reusing an open leaf if present (R8). */
  async activateThinkingPanel(): Promise<ThinkingView | null> {
    let leaf: WorkspaceLeaf | null = this.app.workspace.getLeavesOfType(THINKING_VIEW_TYPE)[0] ?? null;
    if (!leaf) {
      leaf = this.app.workspace.getRightLeaf(false);
      if (!leaf) return null;
      await leaf.setViewState({ type: THINKING_VIEW_TYPE, active: true });
    }
    this.app.workspace.revealLeaf(leaf);
    return leaf.view instanceof ThinkingView ? leaf.view : null;
  }

  private async runThinkingInPanel(topic: string, sourcePath: string): Promise<void> {
    const view = await this.activateThinkingPanel();
    await view?.setTopic(topic, sourcePath);
  }

  /** Fan the one snapshot out to every surface (KTD1). */
  private applySnapshot(snapshot: StateSnapshot): void {
    this.snapshot = snapshot;
    this.statusBar?.update(snapshot);
    for (const leaf of this.app.workspace.getLeavesOfType(SIDEBAR_VIEW_TYPE)) {
      const view = leaf.view;
      if (view instanceof RecallSidebarView) view.draw();
    }
  }

  /** Whether the core "Page preview" plugin is enabled — gates native hover
   *  preview; when off, reference rows fall back to the engine-snippet peek. */
  private pagePreviewEnabled(): boolean {
    const ip = (
      this.app as unknown as {
        internalPlugins?: { getPluginById?(id: string): { enabled?: boolean } | null };
      }
    ).internalPlugins;
    return !!ip?.getPluginById?.("page-preview")?.enabled;
  }

  /** Run thinking-mode for a specific resolved reference (the "think about this
   *  note" menu action). Read-only — opens the thinking surface, never writes. */
  private thinkAboutReference(ref: ResolvedReference): void {
    const sourcePath = ref.file?.path ?? this.app.workspace.getActiveFile()?.path ?? "";
    void this.runThinkingInPanel(ref.display.title, sourcePath);
  }

  /** Right-click menu + drag/copy insertion for a resolvable row. Read-only:
   *  the plugin supplies drag data and clipboard text; the user performs the
   *  drop/paste (R5, R14, R15). */
  private decorateLocalRow(row: HTMLElement, ref: ResolvedReference, sourcePath: string): void {
    const file = ref.file;
    if (!file) return;

    // Native link-drag: set the vault-correct link text; the editor handles the
    // drop. Dropping outside an editor is a harmless no-op (no partial state).
    row.setAttribute("draggable", "true");
    row.addEventListener("dragstart", (evt: DragEvent) => {
      evt.dataTransfer?.setData("text/plain", localLinkText(this.app, file, sourcePath));
    });

    row.addEventListener("contextmenu", (evt) => {
      evt.preventDefault();
      const menu = new Menu();
      menu.addItem((i) =>
        i.setTitle("Open").setIcon("file").onClick(() => void this.app.workspace.getLeaf(false).openFile(file)),
      );
      menu.addItem((i) =>
        i.setTitle("Open in new tab").setIcon("file-plus").onClick(() => void this.app.workspace.getLeaf("tab").openFile(file)),
      );
      menu.addItem((i) =>
        i.setTitle("Open to the side").setIcon("panel-right").onClick(() => void this.app.workspace.getLeaf("split").openFile(file)),
      );
      menu.addSeparator();
      menu.addItem((i) =>
        i.setTitle("Think about this note").setIcon("brain").onClick(() => this.thinkAboutReference(ref)),
      );
      menu.addItem((i) =>
        i.setTitle("Copy as link").setIcon("link").onClick(async () => {
          await navigator.clipboard.writeText(localLinkText(this.app, file, sourcePath));
          new Notice("hypermnesic: link copied");
        }),
      );
      menu.showAtMouseEvent(evt);
    });
  }

  /** Non-local rows offer only "copy path" — no wikilink that resolves to
   *  nothing (R16). */
  private decorateNonLocalRow(row: HTMLElement, ref: ResolvedReference): void {
    row.addEventListener("contextmenu", (evt) => {
      evt.preventDefault();
      const menu = new Menu();
      menu.addItem((i) =>
        i.setTitle("Copy path").setIcon("copy").onClick(async () => {
          await navigator.clipboard.writeText(ref.input.path);
          new Notice("hypermnesic: path copied");
        }),
      );
      menu.showAtMouseEvent(evt);
    });
  }

  private buildRenderDeps(): RenderDeps {
    return {
      app: this.app,
      openFile: (file, newLeaf) => void this.app.workspace.getLeaf(newLeaf).openFile(file),
      pagePreviewEnabled: () => this.pagePreviewEnabled(),
      decorateLocalRow: (row, ref, sourcePath) => this.decorateLocalRow(row, ref, sourcePath),
      decorateNonLocalRow: (row, ref) => this.decorateNonLocalRow(row, ref),
      renderNudge: (host, snapshot, hoverParent) => {
        if (!snapshot.result) return;
        renderNudge(
          host,
          snapshot.result,
          {
            getUrl: () => this.settings.mcpUrl,
            store: this.nudgeStore(),
            threshold: () => this.settings.reinventThreshold,
            activePath: () => this.app.workspace.getActiveViewOfType(MarkdownView)?.file?.path ?? "",
            rowDeps: this.renderDeps,
          },
          hoverParent,
        );
      },
    };
  }

  private createStatusBar(): void {
    const el = this.addStatusBarItem();
    this.statusBar = new StatusBarSurface(el, this.renderDeps, this.snapshot);
    // Remove the body-appended popover on unload (auto-cleanup).
    this.register(() => this.statusBar?.dispose());
  }

  /** Settings-tab hook: re-probe capabilities after a URL change, and re-rank the
   *  visible result so ranking sliders (staleness weight, half-life) and the nudge
   *  threshold apply live without a reload (R18, AE4). */
  onSettingsChanged(): void {
    void this.core.probe();
    void this.reapplyRanking();
  }

  /** Re-run the pipeline for the last query (a block-cache hit — no new MCP call)
   *  so the current settings re-rank the visible result, then fan it out. Falls
   *  back to a repaint when there is no prior result. */
  private async reapplyRanking(): Promise<void> {
    const current = this.snapshot.result;
    if (!current) {
      this.applySnapshot(this.snapshot);
      return;
    }
    try {
      const result = await this.core.run(current.query, current.sourcePath);
      this.applySnapshot(this.machine.success(result));
    } catch {
      this.applySnapshot(this.snapshot);
    }
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
    const raw = (await this.loadData()) as Partial<PluginData> | Partial<HypermnesicSettings> | null;
    // Back-compat: older builds stored the settings object at the top level.
    const hasWrapper = !!raw && typeof raw === "object" && "settings" in raw;
    const stored = hasWrapper
      ? (raw as PluginData).settings
      : (raw as Partial<HypermnesicSettings> | null);
    this.settings = Object.assign({}, DEFAULT_SETTINGS, stored ?? {});
    const muted = hasWrapper ? ((raw as PluginData).mutedNotes ?? []) : [];
    this.mutedNotes = new Set(muted);
  }

  private async persist(): Promise<void> {
    const data: PluginData = { settings: this.settings, mutedNotes: Array.from(this.mutedNotes) };
    await this.saveData(data);
  }

  async saveSettings(): Promise<void> {
    await this.persist();
  }
}
