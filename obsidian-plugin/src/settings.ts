/**
 * src/settings.ts — the settings tab (U41, FR-R21/R22).
 *
 * PluginSettingTab with sentence-case names and setHeading sections: connection
 * (default-EMPTY MCP URL — opt-in off-device send), triggers, surfaces, nudge,
 * ranking, and a read-only trust panel that lists the exact allowlisted read
 * tools. All values persist via saveData; any future credential is read here and
 * NEVER logged. Future MCP OAuth attaches at the protocol-handler seam (not now).
 */
import { App, Plugin, PluginSettingTab, Setting } from "obsidian";
import { DEFAULT_SETTINGS, HypermnesicSettings } from "./types";
import { READ_ONLY_TOOLS } from "./core";

export interface SettingsHostPlugin extends Plugin {
  settings: HypermnesicSettings;
  saveSettings(): Promise<void>;
  /** Re-probe capabilities / refresh surfaces after a settings change. */
  onSettingsChanged?(): void;
}

function toInt(value: string, fallback: number): number {
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) ? n : fallback;
}

function toFloat(value: string, fallback: number): number {
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : fallback;
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
      .setDesc("Idle time after you stop typing before recall fires. Never per-keystroke. Takes effect on reload.")
      .addText((t) =>
        t.setValue(String(this.plugin.settings.pauseMs)).onChange(async (v) => {
          this.plugin.settings.pauseMs = toInt(v, DEFAULT_SETTINGS.pauseMs);
          await this.save();
        }),
      );

    new Setting(containerEl)
      .setName("Result count")
      .setDesc("How many related notes to request and show.")
      .addText((t) =>
        t.setValue(String(this.plugin.settings.resultCount)).onChange(async (v) => {
          this.plugin.settings.resultCount = toInt(v, DEFAULT_SETTINGS.resultCount);
          await this.save();
        }),
      );

    // ── Surfaces ───────────────────────────────────────────────────────────
    new Setting(containerEl).setName("Surfaces").setHeading();

    new Setting(containerEl)
      .setName("Status-bar indicator")
      .setDesc("The calm-primary surface (desktop only). Takes effect on reload.")
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

    new Setting(containerEl)
      .setName("Similarity threshold")
      .setDesc("Show the nudge when the top match's score is at or above this (0–1).")
      .addText((t) =>
        t.setValue(String(this.plugin.settings.reinventThreshold)).onChange(async (v) => {
          this.plugin.settings.reinventThreshold = toFloat(v, DEFAULT_SETTINGS.reinventThreshold);
          await this.save();
        }),
      );

    // ── Ranking ────────────────────────────────────────────────────────────
    new Setting(containerEl).setName("Forgetting curve").setHeading();

    new Setting(containerEl)
      .setName("Recency half-life (days)")
      .setDesc("Staleness reaches 50% after this many days since a note was last written.")
      .addText((t) =>
        t.setValue(String(this.plugin.settings.recencyHalfLifeDays)).onChange(async (v) => {
          this.plugin.settings.recencyHalfLifeDays = toFloat(v, DEFAULT_SETTINGS.recencyHalfLifeDays);
          await this.save();
        }),
      );

    new Setting(containerEl)
      .setName("Staleness weight")
      .setDesc("How strongly staleness reweights relevance, 0 (off) to 1 (strong).")
      .addText((t) =>
        t.setValue(String(this.plugin.settings.stalenessWeight)).onChange(async (v) => {
          this.plugin.settings.stalenessWeight = toFloat(v, DEFAULT_SETTINGS.stalenessWeight);
          await this.save();
        }),
      );

    // ── Trust (read-only display) ────────────────────────────────────────────
    new Setting(containerEl).setName("Read-only guarantee").setHeading();

    new Setting(containerEl)
      .setName("Allowlisted read tools")
      .setDesc(
        "This companion can call only these read tools over the tailnet — and " +
          "never any write tool. It performs no vault writes and retains no note " +
          "text between queries.",
      )
      .addText((t) => {
        t.setValue(Array.from(READ_ONLY_TOOLS).join(", "));
        t.setDisabled(true);
        return t;
      });

    const seam = containerEl.createEl("p", { cls: "hypermnesic-settings-note" });
    seam.setText(
      "Authentication: the tailnet membership is the boundary today. Future MCP " +
        "OAuth will attach at the Obsidian protocol-handler seam (PKCE); it is not " +
        "implemented yet, and no credential is logged.",
    );
  }
}
