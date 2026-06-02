import { describe, it, expect } from "vitest";
import {
  displayModel,
  formatLink,
  normalizeRefPath,
  samePath,
} from "../src/surfaces/reference-model";

describe("normalizeRefPath", () => {
  it("collapses repeated slashes, converts backslashes, trims edges", () => {
    expect(normalizeRefPath("/a//b/c.md/")).toBe("a/b/c.md");
    expect(normalizeRefPath("a\\b")).toBe("a/b");
    expect(normalizeRefPath("  note.md  ")).toBe("note.md");
  });
});

describe("samePath — full-path equality guard (R27)", () => {
  it("is true for identical paths", () => {
    expect(samePath("archive/2021/meeting.md", "archive/2021/meeting.md")).toBe(true);
    expect(samePath("/archive//2021/meeting.md", "archive/2021/meeting.md")).toBe(true);
  });

  it("is false when only the basename matches (mis-resolution case)", () => {
    // Engine asked for archive/2021/meeting.md; the vault resolved a DIFFERENT
    // meeting.md by basename fallback — must NOT be treated as the same note.
    expect(samePath("archive/2021/meeting.md", "inbox/meeting.md")).toBe(false);
  });

  it("is false when the roots diverge", () => {
    expect(samePath("master/projects/foo.md", "projects/foo.md")).toBe(false);
  });
});

describe("displayModel", () => {
  it("nested path → basename title + de-emphasized folder", () => {
    expect(displayModel("a/b/Note Title.md")).toEqual({ title: "Note Title", folder: "a/b" });
  });

  it("root-level note → no folder segment", () => {
    expect(displayModel("Note.md")).toEqual({ title: "Note", folder: "" });
  });

  it("strips only the trailing .md extension", () => {
    expect(displayModel("notes/v1.2.md")).toEqual({ title: "v1.2", folder: "notes" });
  });
});

describe("formatLink — fallback formatter", () => {
  it("renders wikilink form with and without an alias", () => {
    expect(formatLink("a/b.md", undefined, false)).toBe("[[a/b.md]]");
    expect(formatLink("a/b.md", "Alias", false)).toBe("[[a/b.md|Alias]]");
  });

  it("renders markdown form using the alias or derived title", () => {
    expect(formatLink("a/b.md", "Alias", true)).toBe("[Alias](a/b.md)");
    expect(formatLink("a/My Note.md", undefined, true)).toBe("[My Note](a/My%20Note.md)");
  });
});
