/**
 * src/settings.ts — the settings tab (U41 + first-class redesign, FR-R21/R22).
 *
 * PluginSettingTab with sentence-case names and setHeading sections: connection
 * (default-EMPTY MCP URL — opt-in off-device send), triggers, surfaces, nudge,
 * ranking, and a read-only trust panel that lists the exact allowlisted read
 * tools. Bounded ratios render as sliders with a live value; ranking changes
 * apply live (no reload); the allowlist renders as a real read-only list, not a
 * disabled input. All values persist via saveData; any future credential is read
 * here and NEVER logged.
 */
import { App, Plugin, PluginSettingTab, Setting } from "obsidian";
import { DEFAULT_SETTINGS, HypermnesicSettings } from "./types";
import { READ_ONLY_TOOLS } from "./core";

export interface SettingsHostPlugin extends Plugin {
  settings: HypermnesicSettings;
  saveSettings(): Promise<void>;
  /** Re-probe capabilities / re-rank / refresh surfaces after a settings change. */
  onSettingsChanged?(): void;
}

function clampInt(value: string, fallback: number, min: number, max: number): number {
  const n = Number.parseInt(value, 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function clampFloat(value: string, fallback: number, min: number, max: number): number {
  const n = Number.parseFloat(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

export class HypermnesicSettingTab extends PluginSettingTab {
  plugin: SettingsHostPlugin;

  constructor(app: App, plugin: SettingsHostPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  private async save(): Promise<void> {
    await this.plugin.saveSettings();
    this.plugin.onSettingsChanged?.();
  }

  /** A 0–1 ratio as a slider with a live value label (no reload, applies live). */
  private addRatioSlider(
    name: string,
    desc: string,
    get: () => number,
    set: (v: number) => void,
  ): void {
    const setting = new Setting(this.containerEl).setName(name).setDesc(desc);
    let valueEl: HTMLElement | null = null;
    setting.addSlider((s) =>
      s
        .setLimits(0, 1, 0.01)
        .setValue(get())
        .setDynamicTooltip()
        .onChange(async (v) => {
          set(v);
          valueEl?.setText(v.toFixed(2));
          await this.save();
        }),
    );
    valueEl = setting.controlEl.createSpan({
      cls: "hypermnesic-slider-value",
      text: get().toFixed(2),
    });
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    // ── Connection ─────────────────────────────────────────────────────────
    new Setting(containerEl).setName("Connection").setHeading();

    new Setting(containerEl)
      .setName("Tailnet MCP URL")
      .setDesc(
        "The read-only hypermnesic endpoint (a Tailscale address). Empty by " +
          "default — nothing is sent off-device until you set this. A provisioned " +
          "client install pre-fills it.",
      )
      .addText((t) =>
        t
          .setPlaceholder("http://<tailscale-host>:8848/mcp")
          .setValue(this.plugin.settings.mcpUrl)
          .onChange(async (v) => {
            this.plugin.settings.mcpUrl = v.trim();
            await this.save();
          }),
      );

    // ── Triggers ───────────────────────────────────────────────────────────
    new Setting(containerEl).setName("Triggers").setHeading();

    new Setting(containerEl)
      .setName("Pause interval (ms)")
      .setDesc(
        "Idle time after you stop typing before recall fires. Never per-keystroke. " +
          "Changes take effect after reload.",
      )
      .addText((t) =>
        t.setValue(String(this.plugin.settings.pauseMs)).onChange(async (v) => {
          this.plugin.settings.pauseMs = clampInt(v, DEFAULT_SETTINGS.pauseMs, 0, 600000);
          await this.save();
        }),
      );

    new Setting(containerEl)
      .setName("Result count")
      .setDesc("How many related notes to request and show (1–50).")
      .addText((t) =>
        t.setValue(String(this.plugin.settings.resultCount)).onChange(async (v) => {
          this.plugin.settings.resultCount = clampInt(v, DEFAULT_SETTINGS.resultCount, 1, 50);
          await this.save();
        }),
      );

    // ── Surfaces ───────────────────────────────────────────────────────────
    new Setting(containerEl).setName("Surfaces").setHeading();

    new Setting(containerEl)
      .setName("Status-bar indicator")
      .setDesc("The calm-primary surface (desktop only). Changes take effect after reload.")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.showStatusBar).onChange(async (v) => {
          this.plugin.settings.showStatusBar = v;
          await this.save();
        }),
      );

    new Setting(containerEl)
      .setName("Editor inline marker")
      .setDesc("Optional CodeMirror marker on the active block. Off by default.")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.showGutter).onChange(async (v) => {
          this.plugin.settings.showGutter = v;
          await this.save();
        }),
      );

    new Setting(containerEl)
      .setName("Open sidebar on start")
      .setDesc("Reveal the opt-in recall sidebar automatically when Obsidian loads.")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.openSidebarOnLoad).onChange(async (v) => {
          this.plugin.settings.openSidebarOnLoad = v;
          await this.save();
        }),
      );

    // ── Nudge ──────────────────────────────────────────────────────────────
    new Setting(containerEl).setName("Reinvention nudge").setHeading();

    this.addRatioSlider(
      "Similarity threshold",
      "Show the nudge when the top match's score is at or above this (0–1).",
      () => this.plugin.settings.reinventThreshold,
      (v) => (this.plugin.settings.reinventThreshold = v),
    );

    // ── Ranking ────────────────────────────────────────────────────────────
    new Setting(containerEl).setName("Forgetting curve").setHeading();

    new Setting(containerEl)
      .setName("Recency half-life (days)")
      .setDesc("Staleness reaches 50% after this many days since a note was last written.")
      .addText((t) =>
        t.setValue(String(this.plugin.settings.recencyHalfLifeDays)).onChange(async (v) => {
          this.plugin.settings.recencyHalfLifeDays = clampFloat(
            v,
            DEFAULT_SETTINGS.recencyHalfLifeDays,
            0.01,
            36500,
          );
          await this.save();
        }),
      );

    this.addRatioSlider(
      "Staleness weight",
      "How strongly staleness reweights relevance, 0 (off) to 1 (strong). Applies live.",
      () => this.plugin.settings.stalenessWeight,
      (v) => (this.plugin.settings.stalenessWeight = v),
    );

    // ── Trust (read-only display) ────────────────────────────────────────────
    new Setting(containerEl).setName("Read-only guarantee").setHeading();

    new Setting(containerEl)
      .setName("Allowlisted read tools")
      .setDesc(
        "This companion can call only these read tools over the tailnet — and " +
          "never any write tool. It performs no vault writes and retains no note " +
          "text between queries.",
      );
    const tools = containerEl.createEl("ul", { cls: "hypermnesic-tool-list" });
    for (const tool of READ_ONLY_TOOLS) tools.createEl("li", { text: tool });

    const seam = containerEl.createEl("p", { cls: "hypermnesic-settings-note" });
    seam.setText(
      "Authentication: the tailnet membership is the boundary today. Future MCP " +
        "OAuth will attach at the Obsidian protocol-handler seam (PKCE); it is not " +
        "implemented yet, and no credential is logged.",
    );
  }
}
