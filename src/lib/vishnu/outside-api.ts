import { createServerFn } from "@tanstack/react-start";
import { authMiddleware } from "@/lib/auth/middleware";
import type { CallToolResult } from "@/lib/app-data/types";

export type OutsideItem = { title: string; detail: string };

export type OutsideResult = {
  ok: boolean;
  items: OutsideItem[];
  message: string;
  loginUrl?: string;
  pending?: boolean;
};

function textField(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (value && typeof value === "object" && "dateTime" in value) {
      const dateTime = (value as { dateTime?: unknown }).dateTime;
      if (typeof dateTime === "string") return dateTime;
    }
    if (value && typeof value === "object" && "email" in value) {
      const email = (value as { email?: unknown }).email;
      if (typeof email === "string") return email;
    }
  }
  return "";
}

function itemsFrom(data: unknown) {
  const found: OutsideItem[] = [];
  const seen = new Set<string>();
  const visit = (value: unknown, depth: number) => {
    if (!value || depth > 5 || found.length >= 12) return;
    if (Array.isArray(value)) {
      value.forEach((item) => visit(item, depth + 1));
      return;
    }
    if (typeof value !== "object") return;
    const row = value as Record<string, unknown>;
    const title = textField(row, ["subject", "summary", "title", "name", "snippet"]);
    if (title) {
      const detail = textField(row, ["from", "snippet", "description", "start", "date", "mimeType"]);
      const key = `${title}|${detail}`;
      if (!seen.has(key)) {
        seen.add(key);
        found.push({ title: title.slice(0, 180), detail: detail.slice(0, 240) });
      }
    } else {
      Object.values(row).forEach((child) => visit(child, depth + 1));
    }
  };
  visit(data, 0);
  return found;
}

async function readOne(kind: "calendar" | "mail" | "files"): Promise<CallToolResult> {
  const { callTool } = await import("@/lib/app-data/client.server");
  const { ConnectorType, GoogleCalendarTools, GoogleDriveTools } = await import("@/lib/app-data/types");
  const start = new Date();
  const end = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  if (kind === "calendar") {
    return callTool(
      GoogleCalendarTools.search,
      { q: "", query: "", timeMin: start.toISOString(), timeMax: end.toISOString(), maxResults: 8 },
      { connectorType: ConnectorType.GoogleCalendar },
    );
  }
  if (kind === "files") {
    return callTool(
      GoogleDriveTools.search,
      { q: "trashed = false", pageSize: 8 },
      { connectorType: ConnectorType.GoogleDrive },
    );
  }
  const first = await callTool(
    "gmail_search",
    { query: "in:inbox newer_than:14d", maxResults: 8 },
    { connectorType: ConnectorType.Gmail },
  );
  if (first.ok || !first.errorMessage?.toLowerCase().includes("unknown")) return first;
  return callTool(
    "google_gmail_search",
    { query: "in:inbox newer_than:14d", maxResults: 8 },
    { connectorType: ConnectorType.Gmail },
  );
}

export const readConnectors = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => {
    const kind = input && typeof input === "object" && "kind" in input ? (input as { kind?: unknown }).kind : "";
    if (kind !== "calendar" && kind !== "mail" && kind !== "files") throw new Error("Unknown connector");
    return { kind: kind as "calendar" | "mail" | "files" };
  })
  .handler(async ({ data }): Promise<OutsideResult> => {
    const { classifyCallToolError } = await import("@/lib/app-data/errors");
    const result = await readOne(data.kind);
    if (!result.ok) {
      const state = classifyCallToolError(result);
      return {
        ok: false,
        items: [],
        message: state?.message ?? "Could not read that connector.",
        ...(result.loginUrl ? { loginUrl: result.loginUrl } : {}),
        ...(result.pending ? { pending: true } : {}),
      };
    }
    const items = itemsFrom(result.data);
    return {
      ok: true,
      items,
      message: items.length ? `Read ${items.length} from ${data.kind}.` : `Connected, and ${data.kind} had nothing to show.`,
    };
  });
