/**
 * src/surfaces/reference-model.ts — PURE reference helpers (U1, KTD8).
 *
 * Zero Obsidian imports by design: this is the unit-tested core that the edge
 * module (reference.ts) and the renderer (U2) build on. It owns the display
 * model, the full-path-equality check that guards against mis-resolution (R27),
 * and the fallback link formatter. No DOM, no I/O, no Obsidian API.
 */

export type ReferenceKind = "local" | "non-local";

/** The minimal info a reference carries before resolution. Recall passes a
 *  RankedHit (a superset); thinking-mode adapts its related items into this. */
export interface ReferenceInput {
  /** Engine-returned path (vault-root-relative when the corpora align). */
  path: string;
  heading?: string;
  /** ≤280-char engine snippet — the non-local peek's read-only stand-in. */
  snippet?: string;
}

export interface DisplayModel {
  /** Basename without the .md extension — the human title. */
  title: string;
  /** Containing folder, de-emphasized in the UI. "" for a root-level note. */
  folder: string;
}

/**
 * Clean slashes + trim, mirroring Obsidian's normalizePath slash handling, so a
 * full-path equality check is deterministic and testable without the API.
 */
export function normalizeRefPath(path: string): string {
  return path
    .replace(/\\/g, "/")
    .replace(/\/{2,}/g, "/")
    .replace(/^\/+|\/+$/g, "")
    .trim();
}

/**
 * True only when two paths name the SAME note (full-path equality). Guards
 * against getFirstLinkpathDest's basename/shortest-path fallback resolving the
 * engine path to a *different* local note and presenting it as authoritative
 * (R27) — under-resolution is honest (a muted row); mis-resolution is not.
 */
export function samePath(a: string, b: string): boolean {
  return normalizeRefPath(a) === normalizeRefPath(b);
}

/** Title (basename sans .md) + de-emphasized folder for a vault path. */
export function displayModel(path: string): DisplayModel {
  const clean = normalizeRefPath(path);
  const slash = clean.lastIndexOf("/");
  const base = slash >= 0 ? clean.slice(slash + 1) : clean;
  const folder = slash >= 0 ? clean.slice(0, slash) : "";
  return { title: base.replace(/\.md$/i, ""), folder };
}

/**
 * Deterministic fallback link formatter for the cases Obsidian's native
 * generator can't serve (a non-resolvable path we still want to format, or a
 * test). Real local files use fileManager.generateMarkdownLink (R15) in the
 * edge module so the user's link-format and relative/shortest preference win.
 */
export function formatLink(
  path: string,
  alias: string | undefined,
  useMarkdownLinks: boolean,
): string {
  const clean = normalizeRefPath(path);
  if (useMarkdownLinks) {
    return `[${alias ?? displayModel(clean).title}](${encodeURI(clean)})`;
  }
  return alias ? `[[${clean}|${alias}]]` : `[[${clean}]]`;
}
