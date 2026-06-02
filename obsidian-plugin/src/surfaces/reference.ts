/**
 * src/surfaces/reference.ts — the Obsidian-API edge for reference resolution and
 * link generation (U1) plus the shared reference-row primitive (U2, KTD2).
 *
 * Every surface (recall popover, sidebar, thinking panel, nudge) renders a note
 * reference through `renderReference`, so links, Page-preview hover, the context
 * menu, insertion, and the local/non-local branch are implemented once and
 * inherited. Surface chrome (channel chips, staleness, think-deeper, mute) stays
 * in each surface — the primitive owns only the reference itself.
 *
 * READ-ONLY: this module resolves and renders existing notes and produces link
 * TEXT for the user to paste/drop. It never imports a CodeMirror editor module
 * and never calls an editor/vault write — the static scan in
 * tests/test_obsidian_plugin.py asserts both (R26).
 */
import { App, HoverParent, TFile, normalizePath, setIcon } from "obsidian";
import { DisplayModel, ReferenceInput, ReferenceKind, displayModel, samePath } from "./reference-model";

export interface ResolvedReference {
  input: ReferenceInput;
  kind: ReferenceKind;
  /** The resolved local file when kind === "local", else null. */
  file: TFile | null;
  display: DisplayModel;
}

/** Where to open a note. `false` = current leaf, mirroring Obsidian's modifiers. */
export type NewLeaf = false | "tab" | "split";

export interface ReferenceRowDeps {
  app: App;
  /** Read-only navigation by the resolved TFile — never `openLinkText` on a raw
   *  engine path, which would create-on-miss (R6, R27). */
  openFile(file: TFile, newLeaf: NewLeaf): void;
  /** Whether the core Page-preview plugin is enabled; gates native hover (KTD4). */
  pagePreviewEnabled(): boolean;
  /** U3: attach the context menu + drag + copy-as-link to a local row. */
  decorateLocalRow?(row: HTMLElement, ref: ResolvedReference, sourcePath: string): void;
  /** U3: attach copy-path to a non-local row. */
  decorateNonLocalRow?(row: HTMLElement, ref: ResolvedReference): void;
}

/** Typed `hover-link` payload — the event is an untyped `trigger` convention, so
 *  pinning the shape here turns a field-name typo into a compile error (KTD4). */
interface HoverLinkEvent {
  event: MouseEvent;
  source: string;
  hoverParent: HoverParent;
  targetEl: HTMLElement;
  linktext: string;
  sourcePath: string;
}

const HOVER_SOURCE = "hypermnesic-companion";

/**
 * Resolve an engine path against the vault, enforcing full-path equality so a
 * basename collision never yields a confident link to the wrong note (KTD3,
 * R27). `sourcePath` is the note the result was computed for (KTD10).
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

/**
 * Render ONE reference into `host`. Returns the row's primary focusable element
 * so the surface can manage roving-tabindex focus. Local references become
 * native links with Page-preview hover; non-local references become honest muted
 * rows with a snippet peek — never a broken or note-creating link.
 */
export function renderReference(
  host: HTMLElement,
  ref: ResolvedReference,
  sourcePath: string,
  deps: ReferenceRowDeps,
  hoverParent: HoverParent | null,
): HTMLElement {
  return ref.kind === "local" && ref.file
    ? renderLocalRow(host, ref, ref.file, sourcePath, deps, hoverParent)
    : renderNonLocalRow(host, ref, deps);
}

function renderLocalRow(
  host: HTMLElement,
  ref: ResolvedReference,
  file: TFile,
  sourcePath: string,
  deps: ReferenceRowDeps,
  hoverParent: HoverParent | null,
): HTMLElement {
  const link = host.createEl("a", {
    cls: "internal-link hypermnesic-ref-link",
    text: ref.display.title,
    href: "#",
  });
  link.setAttribute("aria-label", ariaLabel(ref));
  appendFolderAndHeading(host, ref);

  link.addEventListener("click", (evt) => {
    evt.preventDefault();
    deps.openFile(file, leafFromEvent(evt));
  });
  link.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter" || evt.key === " ") {
      evt.preventDefault();
      deps.openFile(file, false);
    }
  });
  link.addEventListener("mouseover", (evt) => {
    if (deps.pagePreviewEnabled() && hoverParent) {
      const payload: HoverLinkEvent = {
        event: evt,
        source: HOVER_SOURCE,
        hoverParent,
        targetEl: link,
        linktext: file.path,
        sourcePath,
      };
      deps.app.workspace.trigger("hover-link", payload);
    }
  });

  // When Page-preview is disabled, a local row would otherwise be hover-dead;
  // give it the same snippet peek non-local rows use (AE6).
  if (!deps.pagePreviewEnabled() && ref.input.snippet) {
    attachSnippetPeek(host, ref.input.snippet, true);
  }

  deps.decorateLocalRow?.(host, ref, sourcePath);
  return link;
}

function renderNonLocalRow(
  host: HTMLElement,
  ref: ResolvedReference,
  deps: ReferenceRowDeps,
): HTMLElement {
  const row = host.createSpan({ cls: "hypermnesic-ref-nonlocal" });
  row.setAttribute("tabindex", "-1");
  row.setAttribute("aria-label", `${ref.display.title}, not in this vault`);

  const icon = row.createSpan({ cls: "hypermnesic-ref-icon" });
  icon.setAttribute("aria-hidden", "true");
  setIcon(icon, "file-question");

  row.createSpan({ cls: "hypermnesic-ref-title", text: ref.display.title });
  row.createSpan({ cls: "hypermnesic-not-in-vault", text: "not in this vault" });
  appendFolderAndHeading(host, ref);

  if (ref.input.snippet) attachSnippetPeek(host, ref.input.snippet, true);
  deps.decorateNonLocalRow?.(row, ref);
  return row;
}

function appendFolderAndHeading(host: HTMLElement, ref: ResolvedReference): void {
  if (ref.display.folder) {
    host.createSpan({ cls: "hypermnesic-folder", text: ref.display.folder });
  }
  if (ref.input.heading) {
    host.createSpan({ cls: "hypermnesic-heading", text: ` — ${ref.input.heading}` });
  }
}

function ariaLabel(ref: ResolvedReference): string {
  const where = ref.display.folder ? `, in ${ref.display.folder}` : "";
  const heading = ref.input.heading ? `, ${ref.input.heading}` : "";
  return `${ref.display.title}${heading}${where}`;
}

function leafFromEvent(evt: MouseEvent | KeyboardEvent): NewLeaf {
  if (!(evt.metaKey || evt.ctrlKey)) return false;
  return evt.shiftKey ? "split" : "tab";
}

/** A collapsed snippet peek — the read-only stand-in for Page-preview on
 *  non-local rows, and the fallback for local rows when Page-preview is off. */
function attachSnippetPeek(host: HTMLElement, snippet: string, hoverExpand: boolean): void {
  const wrap = host.createDiv({ cls: "hypermnesic-peek" });
  const toggle = wrap.createEl("button", { cls: "hypermnesic-peek-toggle", text: "Show snippet" });
  toggle.setAttribute("aria-expanded", "false");
  const body = wrap.createEl("blockquote", { cls: "hypermnesic-peek-body", text: snippet });
  body.toggle(false);

  let open = false;
  const set = (next: boolean): void => {
    open = next;
    body.toggle(open);
    toggle.setText(open ? "Hide snippet" : "Show snippet");
    toggle.setAttribute("aria-expanded", String(open));
  };
  toggle.addEventListener("click", () => set(!open));
  if (hoverExpand) {
    host.addEventListener("mouseover", () => {
      if (!open) set(true);
    });
  }
}

/** Roving-tabindex arrow navigation across a list of row focusables (R13). */
export function enableRovingFocus(container: HTMLElement, focusables: HTMLElement[]): void {
  if (focusables.length === 0) return;
  focusables.forEach((el, i) => el.setAttribute("tabindex", i === 0 ? "0" : "-1"));
  container.addEventListener("keydown", (evt: KeyboardEvent) => {
    if (evt.key !== "ArrowDown" && evt.key !== "ArrowUp") return;
    evt.preventDefault();
    const current = focusables.findIndex((el) => el === document.activeElement);
    const start = current < 0 ? 0 : current;
    const next = Math.max(0, Math.min(focusables.length - 1, start + (evt.key === "ArrowDown" ? 1 : -1)));
    focusables.forEach((el, i) => el.setAttribute("tabindex", i === next ? "0" : "-1"));
      focusables[next]?.focus();
  });
}
