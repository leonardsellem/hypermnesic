/**
 * src/surfaces/gutter.ts — optional CM6 inline marker (U38, R-3).
 *
 * A minimal CodeMirror-6 editor extension (registered via
 * registerEditorExtension, so Obsidian auto-cleans it on unload) that marks the
 * cursor's block and appends a small "related count" widget when the gutter is
 * enabled and the core has related notes. It pulls from a provider — it never
 * queries the engine and never mutates the document. The status-bar surface is
 * the calm default; this gutter is opt-in (showGutter, default off).
 */
import { Extension, RangeSetBuilder } from "@codemirror/state";
import {
  Decoration,
  DecorationSet,
  EditorView,
  ViewPlugin,
  ViewUpdate,
  WidgetType,
} from "@codemirror/view";

export interface GutterProvider {
  /** settings.showGutter */
  enabled(): boolean;
  /** related count for the user's current writing context */
  count(): number;
}

class RelatedCountWidget extends WidgetType {
  constructor(private n: number) {
    super();
  }
  eq(other: RelatedCountWidget): boolean {
    return other.n === this.n;
  }
  toDOM(): HTMLElement {
    const el = document.createElement("span");
    el.className = "hypermnesic-inline-marker";
    el.setAttribute("aria-hidden", "true");
    el.title = `${this.n} related note${this.n === 1 ? "" : "s"}`;
    el.textContent = ` ◆${this.n}`;
    return el;
  }
  ignoreEvent(): boolean {
    return true;
  }
}

function buildDecorations(view: EditorView, provider: GutterProvider): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  if (!provider.enabled()) return builder.finish();
  const n = provider.count();
  if (n <= 0) return builder.finish();
  const line = view.state.doc.lineAt(view.state.selection.main.head);
  builder.add(line.from, line.from, Decoration.line({ class: "hypermnesic-active-block" }));
  builder.add(line.to, line.to, Decoration.widget({ widget: new RelatedCountWidget(n), side: 1 }));
  return builder.finish();
}

/** The editor extension. Refreshes on selection/doc/viewport change. */
export function hypermnesicGutter(provider: GutterProvider): Extension {
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;
      constructor(view: EditorView) {
        this.decorations = buildDecorations(view, provider);
      }
      update(update: ViewUpdate): void {
        if (update.docChanged || update.selectionSet || update.viewportChanged) {
          this.decorations = buildDecorations(update.view, provider);
        }
      }
    },
    { decorations: (plugin) => plugin.decorations },
  );
}
