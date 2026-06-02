/**
 * src/settings.ts — the settings tab. Phase A wires the default-empty MCP URL
 * (opt-in off-device send); Phase D (U41) expands it with the full toggle set,
 * the allowlisted-read-tools display, and the trust layer.
 */
import { App, Plugin, PluginSettingTab, Setting } from "obsidian";
import { HypermnesicSettings } from "./types";

/**
 * Structural shape the settings tab needs from the plugin. Defined here so
 * settings.ts does not import main.ts (which imports this file) — no cycle.
 */
export interface SettingsHostPlugin extends Plugin {
  settings: HypermnesicSettings;
  saveSettings(): Promise<void>;
}

export class HypermnesicSettingTab extends PluginSettingTab {
  plugin: SettingsHostPlugin;

  constructor(app: App, plugin: SettingsHostPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("Tailnet MCP URL")
      .setDesc(
        "The read-only hypermnesic endpoint (a Tailscale address). Empty by " +
          "default — nothing is sent off-device until you set this.",
      )
      .addText((t) =>
        t
          .setPlaceholder("http://<tailscale-host>:8848/mcp")
          .setValue(this.plugin.settings.mcpUrl)
          .onChange(async (v) => {
            this.plugin.settings.mcpUrl = v.trim();
            await this.plugin.saveSettings();
          }),
      );
  }
}
