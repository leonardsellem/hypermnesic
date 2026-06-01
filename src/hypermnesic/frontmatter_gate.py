"""U8 — frontmatter byte-preservation gate ("diff-or-die"). [R9]

A write may only change the lines it was asked to change. Round-trip-preserving
YAML (ruamel) keeps untouched keys byte-identical — scalar dates stay scalar, key
order and Tolaria ``_``-prefixed properties are preserved. The **guard** then
diffs the result and **aborts** (surfacing the offending diff) if any
*un-requested* frontmatter key changed — the trust foundation that makes
review-gated maintenance safe (and prevents the Basic-Memory
``ensure_frontmatter_on_sync`` churn).
"""

from __future__ import annotations

import difflib
import re
from io import StringIO

from ruamel.yaml import YAML

_FM_RE = re.compile(r"\A---\n(.*?\n)---\n(.*)\Z", re.DOTALL)
_KEY_RE = re.compile(r"^([^\s#][^:]*):")


class FrontmatterDriftError(Exception):
    """Raised when a write would change frontmatter lines it was not asked to."""

    def __init__(self, keys, diff: str):
        self.keys = set(keys)
        self.diff = diff
        super().__init__(f"unrequested frontmatter drift on {sorted(self.keys)}:\n{diff}")


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter-inner-YAML, body). frontmatter is None if absent.

    Reconstruct exactly with ``"---\\n" + fm + "---\\n" + body``.
    """
    m = _FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), m.group(2)


def _key_blocks(fm: str) -> tuple[list[str], dict[str, list[str]]]:
    order: list[str] = []
    blocks: dict[str, list[str]] = {}
    cur = "\x00preamble"
    for line in fm.splitlines(keepends=True):
        m = _KEY_RE.match(line)
        if m:
            cur = m.group(1)
            if cur not in blocks:
                blocks[cur] = []
                order.append(cur)
        blocks.setdefault(cur, []).append(line)
    return order, blocks


def changed_keys(orig_fm: str, new_fm: str) -> set[str]:
    """Top-level frontmatter keys whose lines changed (incl. add/remove/reorder)."""
    o_order, o = _key_blocks(orig_fm)
    n_order, n = _key_blocks(new_fm)
    changed = {k for k in set(o) | set(n) if o.get(k) != n.get(k)}
    common_o = [k for k in o_order if k in n]
    common_n = [k for k in n_order if k in o]
    if common_o != common_n:  # reordering is drift
        changed |= set(common_o) | set(common_n)
    return {k for k in changed if k != "\x00preamble"} | (
        {"<preamble>"} if o.get("\x00preamble") != n.get("\x00preamble") else set())


def assert_only_changed(orig_fm: str, new_fm: str, allowed) -> None:
    extra = changed_keys(orig_fm, new_fm) - set(allowed)
    if extra:
        diff = "".join(difflib.unified_diff(
            orig_fm.splitlines(keepends=True), new_fm.splitlines(keepends=True),
            "frontmatter (before)", "frontmatter (after)"))
        raise FrontmatterDriftError(extra, diff)


def _yaml() -> YAML:
    y = YAML()  # round-trip mode
    y.preserve_quotes = True
    y.width = 1 << 30  # never line-wrap
    # Match the vault's nested style (`tags:` then `  - item`) so editing one key
    # never reflows an untouched block. Docs in a different style will simply
    # abort (diff-or-die) rather than churn — the safe failure mode.
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def gated_edit(original: str, *, body: str | None = None,
               set_fields: dict | None = None,
               delete_fields: list | None = None) -> str:
    """Return the edited text, or raise FrontmatterDriftError.

    ``body`` replaces the body (None = unchanged). ``set_fields`` / ``delete_fields``
    change only those frontmatter keys; any collateral change aborts.
    """
    fm_inner, orig_body = split_frontmatter(original)
    new_body = orig_body if body is None else body
    if fm_inner is None:
        if set_fields or delete_fields:
            raise ValueError("no frontmatter to edit")
        return new_body

    requested = set(set_fields or {}) | set(delete_fields or [])
    if requested:
        yaml = _yaml()
        data = yaml.load(fm_inner)
        for k, v in (set_fields or {}).items():
            data[k] = v
        for k in (delete_fields or []):
            if k in data:
                del data[k]
        buf = StringIO()
        yaml.dump(data, buf)
        new_fm = buf.getvalue()
    else:
        new_fm = fm_inner

    assert_only_changed(fm_inner, new_fm, allowed=requested)  # diff-or-die
    return "---\n" + new_fm + "---\n" + new_body
