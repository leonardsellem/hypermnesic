/**
 * src/core.ts — the single network-egress + read-only allowlist for the
 * hypermnesic companion.
 *
 * Every MCP call the plugin makes goes through callTool() here, and callTool()
 * refuses any tool not in READ_ONLY_TOOLS. This is the structural read-only
 * guarantee: the plugin can reach the engine's read tools and nothing else —
 * never the master-only commit_note. The static test in
 * tests/test_obsidian_plugin.py pins the allowlist string below and scans the
 * whole plugin tree (main.ts + src/) for vault-write calls.
 *
 * It also never transmits anything off-device until the user configures an MCP
 * URL: an empty URL short-circuits before any requestUrl (DEP-R17).
 *
 * NOTE (U36): the retrieval pipeline (cursor-window, block-hash cache, ranking)
 * is layered on in Phase B; Phase A establishes the egress + allowlist + types.
 */
import { requestUrl } from "obsidian";

/**
 * Hard allowlist of callable MCP tools — mirrors the server's READ_TOOL_NAMES.
 * The write tool commit_note is registered only on a write-enabled master and is
 * structurally unreachable from this client.
 */
export const READ_ONLY_TOOLS = new Set(["search", "build_context"]);

/** A single related-note hit (the engine's shipped `search` hit shape). */
export interface Hit {
  path: string;
  heading: string;
  score: number;
  /** sorted subset of: lexical | dense | doc */
  channels: string[];
  /** ≤280 chars */
  snippet: string;
  /** epoch seconds (git committer-time of the newest commit touching path);
   *  null when untracked. The companion derives its own decay from this. */
  recency: number | null;
}

export interface SearchResponse {
  query: string;
  degraded_lexical_only: boolean;
  manual_reindex_recommended: boolean;
  hits: Hit[];
}

export interface ThinkResponse {
  topic: string;
  /** Always false — the observable no-write assertion the engine emits. */
  wrote: boolean;
  related: Array<Record<string, unknown>>;
  context: unknown;
  questions: string[];
  tensions: string[];
  degraded?: boolean;
  manual_reindex_recommended?: boolean;
}

export interface ContextResponse {
  start: string;
  depth: number;
  context: unknown;
  manual_reindex_recommended: boolean;
}

/** Refusal raised when code asks for a tool outside the read-only allowlist. */
export class ReadOnlyViolation extends Error {}

/** Raised when no MCP URL is configured — the opt-in off-device guard. */
export class NoEndpointError extends Error {}

const RPC_HEADERS = { Accept: "application/json, text/event-stream" };

/**
 * JSON-RPC tools/call over Plan 1's single-JSON streamable-http serve. requestUrl
 * is buffered/non-streaming, which works because the server defaults to
 * json_response=True. READ tools only; an empty URL transmits nothing.
 */
export async function callTool(
  url: string,
  tool: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  if (!READ_ONLY_TOOLS.has(tool)) {
    throw new ReadOnlyViolation(
      `hypermnesic companion is read-only; refusing tool '${tool}'`,
    );
  }
  if (!url.trim()) {
    throw new NoEndpointError("no MCP URL configured — nothing sent off-device");
  }
  const res = await requestUrl({
    url,
    method: "POST",
    contentType: "application/json",
    headers: RPC_HEADERS,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: { name: tool, arguments: args },
    }),
  });
  return res.json;
}

/** FastMCP returns tool output as a content array of JSON text parts. */
export function parseToolResult<T = unknown>(resp: unknown): T | null {
  try {
    const content = (resp as { result?: { content?: unknown[] } })?.result?.content ?? [];
    const textPart = (content as Array<{ type?: string; text?: string }>).find(
      (c) => c?.type === "text",
    );
    return textPart?.text ? (JSON.parse(textPart.text) as T) : null;
  } catch {
    return null;
  }
}

/** tools/list for the capability handshake (KTD4). Empty URL → no probe. */
export async function listTools(url: string): Promise<string[]> {
  if (!url.trim()) return [];
  const res = await requestUrl({
    url,
    method: "POST",
    contentType: "application/json",
    headers: RPC_HEADERS,
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }),
  });
  const tools = (res.json as { result?: { tools?: Array<{ name?: string }> } })?.result?.tools ?? [];
  return tools.map((t) => t?.name).filter((n): n is string => typeof n === "string");
}
