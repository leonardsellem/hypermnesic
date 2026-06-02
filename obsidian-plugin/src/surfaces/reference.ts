/**
 * src/surfaces/reference.ts — the Obsidian-API edge for reference resolution and
 * link generation (U1). The shared reference-row renderer (renderReference) is
 * added in U2.
 *
 * READ-ONLY: this module resolves and renders existing notes and produces link
 * TEXT for the user to paste/drop. It never imports a CodeMirror editor module
 * and never calls an editor/vault write — the static scan in
 * tests/test_obsidian_plugin.py asserts both (R26).
 */
import { App, TFile, normalizePath } from "obsidian";
import { DisplayModel, ReferenceInput, ReferenceKind, displayModel, samePath } from "./reference-model";

export interface ResolvedReference {
  input: ReferenceInput;
  kind: ReferenceKind;
  /** The resolved local file when kind === "local", else null. */
  file: TFile | null;
  display: DisplayModel;
}

/**
 * Resolve an engine path against the vault, enforcing full-path equality so a
 * basename collision never yields a confident link to the wrong note (KTD3,
 * R27). `sourcePath` is the note the result was computed for (KTD10) — it
 * disambiguates same-named notes and feeds the native link generator.
 */
export function resolveReference(
  app: App,
  input: ReferenceInput,
  sourcePath: string,
): ResolvedReference {
  const dest = app.metadataCache.getFirstLinkpathDest(normalizePath(input.path), sourcePath);
  const isLocal = dest instanceof TFile && samePath(dest.path, input.path);
  return {
    input,
    kind: isLocal ? "local" : "non-local",
    file: isLocal ? dest : null,
    display: displayModel(input.path),
  };
}

/** Vault-correct link text for a resolved local file, honoring the user's
 *  wikilink-vs-markdown setting via the native primitive (R15). */
export function localLinkText(app: App, file: TFile, sourcePath: string): string {
  return app.fileManager.generateMarkdownLink(file, sourcePath);
}
