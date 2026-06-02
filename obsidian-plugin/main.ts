/**
 * U25 — hypermnesic companion: retrieval-while-writing (H2). [R6/H2/KD2]
 *
 * A thin DESKTOP plugin that, on a debounce, sends the current note's text to the
 * existing tailnet `search` / `build_context` MCP and renders a "related notes /
 * you may be reinventing [[X]]" sidebar.
 *
 * STRICTLY READ-ONLY (KD2/R10): this plugin issues ONLY the two read tools
 * (`search`, `build_context`) over the MCP and performs NO vault writes — no
 * `vault.modify/create/delete/append/trash`, no `adapter.write`. Any write the
 * owner chooses to make flows through the U18 git proposal path, never from here.
 * It also retains no note text between calls (the buffer is local to each call).
 */
import {
  ItemView,
  MarkdownView,
  Plugin,
  PluginSettingTab,
  Setting,
  WorkspaceLeaf,
  debounce,
  requestUrl,
} from "obsidian";

const VIEW_TYPE = "hypermnesic-related";

interface HypermnesicSettings {
  mcpUrl: string; // tailnet MCP endpoint, e.g. http://100.x.y.z:8848/mcp
  debounceMs: number;
  resultCount: number;
  reinventThreshold: number; // similarity above which to warn "reinventing [[X]]"
}

const DEFAULT_SETTINGS: HypermnesicSettings = {
  mcpUrl: "http://100.103.0.55:8848/mcp",
  debounceMs: 1200,
  resultCount: 8,
  reinventThreshold: 0.85,
};

interface Hit {
  path: string;
  heading: string;
  score: number;
  snippet: string;
}

/** Minimal JSON-RPC call to a FastMCP streamable-http tool. READ tools only. */
async function callTool(url: string, tool: string, args: Record<string, unknown>): Promise<any> {
  // Allowlist of callable tools — a hard guarantee this client is read-only.
  const READ_ONLY_TOOLS = new Set(["search", "build_context"]);
  if (!READ_ONLY_TOOLS.has(tool)) {
    throw new Error(`hypermnesic companion is read-only; refusing tool '${tool}'`);
  }
  const body = {
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: { name: tool, arguments: args },
  };
  const res = await requestUrl({
    url,
    method: "POST",
    contentType: "application/json",
    headers: { Accept: "application/json, text/event-stream" },
    body: JSON.stringify(body),
  });
  return res.json;
}

class RelatedView extends ItemView {
  plugin: HypermnesicPlugin;

  constructor(leaf: WorkspaceLeaf, plugin: HypermnesicPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE;
  }
  getDisplayText(): string {
    return "hypermnesic — related";
  }
  getIcon(): string {
    return "links-coming-in";
  }

  async onOpen(): Promise<void> {
    this.render([], null, "idle");
  }

  /** Render related notes + an optional "reinventing" warning. Pure DOM, no writes. */
  render(hits: Hit[], warning: string | null, state: "idle" | "loading" | "error" | "ok"): void {
    const root = this.containerEl.children[1];
    root.empty();
    root.createEl("h4", { text: "Related notes" });

    if (state === "loading") {
      root.createEl("div", { text: "thinking…", cls: "hypermnesic-status" });
      return;
    }
    if (state === "error") {
      root.createEl("div", {
        text: "offline — could not reach the tailnet index",
        cls: "hypermnesic-status",
      });
      return;
    }
    if (warning) {
      const w = root.createEl("div", { cls: "hypermnesic-warning" });
      w.createEl("strong", { text: "⚠ You may be reinventing: " });
      w.createSpan({ text: warning });
    }
    if (hits.length === 0) {
      root.createEl("div", { text: "nothing related yet", cls: "hypermnesic-status" });
      return;
    }
    const list = root.createEl("ul", { cls: "hypermnesic-related-list" });
    for (const h of hits) {
      const li = list.createEl("li");
      const a = li.createEl("a", { text: h.path, cls: "internal-link" });
      a.addEventListener("click", (evt) => {
        evt.preventDefault();
        // read-only navigation: open the existing note, never create one
        this.app.workspace.openLinkText(h.path, "", false);
      });
      if (h.heading) li.createSpan({ text: ` — ${h.heading}` });
    }
  }
}

export default class HypermnesicPlugin extends Plugin {
  settings: HypermnesicSettings = DEFAULT_SETTINGS;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.registerView(VIEW_TYPE, (leaf) => new RelatedView(leaf, this));
    this.addRibbonIcon("links-coming-in", "hypermnesic related notes", () => this.activateView());
    this.addCommand({
      id: "open-hypermnesic-related",
      name: "Open related-notes panel",
      callback: () => this.activateView(),
    });
    this.addSettingTab(new HypermnesicSettingTab(this.app, this));

    const onChange = debounce(
      () => void this.refresh(),
      this.settings.debounceMs,
      true,
    );
    this.registerEvent(this.app.workspace.on("editor-change", () => onChange()));
  }

  onunload(): void {
    this.app.workspace.detachLeavesOfType(VIEW_TYPE);
  }

  async activateView(): Promise<void> {
    this.app.workspace.detachLeavesOfType(VIEW_TYPE);
    const leaf = this.app.workspace.getRightLeaf(false);
    if (leaf) {
      await leaf.setViewState({ type: VIEW_TYPE, active: true });
      this.app.workspace.revealLeaf(leaf);
    }
  }

  /** Read the active note, query the read-only MCP, render. No text is retained. */
  async refresh(): Promise<void> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE);
    if (!view || leaves.length === 0) return;
    const panel = leaves[0].view as RelatedView;

    let text = view.editor.getValue().slice(0, 4000); // bounded query; local to this call
    const activePath = view.file?.path ?? "";
    if (!text.trim()) {
      panel.render([], null, "ok");
      text = "";
      return;
    }

    panel.render([], null, "loading");
    try {
      const resp = await callTool(this.settings.mcpUrl, "search", {
        query: text,
        k: this.settings.resultCount,
      });
      const payload = parseToolResult(resp);
      const hits: Hit[] = (payload?.hits ?? [])
        .filter((h: Hit) => h.path !== activePath)
        .slice(0, this.settings.resultCount);
      const top = hits[0];
      const warning =
        top && top.score >= this.settings.reinventThreshold ? `[[${top.path}]]` : null;
      panel.render(hits, warning, "ok");
    } catch (e) {
      panel.render([], null, "error");
    } finally {
      text = ""; // retain no note text between calls
    }
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }
  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }
}

/** FastMCP returns tool output as a content array of JSON text parts. */
function parseToolResult(resp: any): any {
  try {
    const content = resp?.result?.content ?? [];
    const textPart = content.find((c: any) => c.type === "text");
    return textPart ? JSON.parse(textPart.text) : null;
  } catch {
    return null;
  }
}

class HypermnesicSettingTab extends PluginSettingTab {
  plugin: HypermnesicPlugin;
  constructor(app: any, plugin: HypermnesicPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    new Setting(containerEl)
      .setName("Tailnet MCP URL")
      .setDesc("The read-only hypermnesic MCP endpoint (a Tailscale address).")
      .addText((t) =>
        t.setValue(this.plugin.settings.mcpUrl).onChange(async (v) => {
          this.plugin.settings.mcpUrl = v;
          await this.plugin.saveSettings();
        }),
      );
    new Setting(containerEl).setName("Debounce (ms)").addText((t) =>
      t.setValue(String(this.plugin.settings.debounceMs)).onChange(async (v) => {
        this.plugin.settings.debounceMs = Number(v) || DEFAULT_SETTINGS.debounceMs;
        await this.plugin.saveSettings();
      }),
    );
  }
}
