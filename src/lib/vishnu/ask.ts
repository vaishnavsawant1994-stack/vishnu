import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { authMiddleware } from "@/lib/auth/middleware";
import type { AskResult, MemoryKind, Proposal } from "./types";

const payloadSchema = z.object({
  ownerName: z.string().max(80),
  autonomy: z.enum(["observe", "suggest", "ask", "act"]),
  emergency: z.boolean(),
  messages: z
    .array(
      z.object({
        role: z.enum(["user", "assistant"]),
        content: z.string().max(4000),
      }),
    )
    .max(12),
  memories: z
    .array(
      z.object({
        title: z.string().max(140),
        body: z.string().max(500),
        kind: z.string().max(24),
      }),
    )
    .max(10),
  knowledge: z
    .array(
      z.object({
        title: z.string().max(140),
        excerpt: z.string().max(400),
      }),
    )
    .max(6),
  tasks: z
    .array(
      z.object({
        title: z.string().max(180),
        done: z.boolean(),
        due: z.string().max(80).optional(),
      }),
    )
    .max(12),
  projects: z
    .array(
      z.object({
        title: z.string().max(120),
        status: z.string().max(24),
        next: z.string().max(200),
      }),
    )
    .max(8),
});

const KINDS = new Set<MemoryKind>(["fact", "preference", "person", "note"]);

function asKind(value: unknown): MemoryKind {
  return typeof value === "string" && KINDS.has(value as MemoryKind) ? (value as MemoryKind) : "fact";
}

function parseActions(value: unknown): Proposal[] {
  if (!Array.isArray(value)) return [];
  const actions: Proposal[] = [];
  for (const item of value.slice(0, 4)) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const type = row.type;
    if (type === "remember" && typeof row.title === "string" && typeof row.body === "string") {
      actions.push({
        type: "remember",
        title: row.title.slice(0, 120),
        body: row.body.slice(0, 500),
        kind: asKind(row.kind),
        risk: "low",
      });
    } else if (type === "task" && typeof row.title === "string") {
      actions.push({
        type: "task",
        title: row.title.slice(0, 180),
        due: typeof row.due === "string" ? row.due.slice(0, 80) : undefined,
        risk: "low",
      });
    } else if (type === "knowledge" && typeof row.title === "string" && typeof row.body === "string") {
      actions.push({
        type: "knowledge",
        title: row.title.slice(0, 140),
        body: row.body.slice(0, 2000),
        risk: "low",
      });
    } else if (type === "forget" && typeof row.title === "string") {
      actions.push({ type: "forget", title: row.title.slice(0, 120), risk: "consequential" });
    }
  }
  return actions;
}

function parseModel(raw: string): { text: string; actions: Proposal[] } {
  const cleaned = raw.trim().replace(/^```(?:json)?\s*/i, "").replace(/```$/i, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) return { text: raw.trim().slice(0, 4000), actions: [] };
  try {
    const data = JSON.parse(cleaned.slice(start, end + 1)) as { text?: unknown; actions?: unknown };
    const text = typeof data.text === "string" && data.text.trim() ? data.text.trim() : raw.trim();
    return { text: text.slice(0, 4000), actions: parseActions(data.actions) };
  } catch {
    return { text: raw.trim().slice(0, 4000), actions: [] };
  }
}

async function complete(apiKey: string, body: unknown) {
  const res = await fetch("https://api.x.ai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(28000),
  });
  return res;
}

export const aiAvailable = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async () => {
  return { available: Boolean(process.env.XAI_API_KEY) };
});

export const askVishnu = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => payloadSchema.parse(input))
  .handler(async ({ data }): Promise<AskResult> => {
    const apiKey = process.env.XAI_API_KEY;
    if (!apiKey) return { ok: false, error: "Cloud mind is not available" };

    const context = {
      owner: data.ownerName,
      autonomy: data.autonomy,
      emergencyStop: data.emergency,
      memories: data.memories,
      knowledge: data.knowledge,
      openTasks: data.tasks,
      projects: data.projects,
    };

    const system = [
      "You are Vishnu, a single-owner personal assistant.",
      "Voice: calm, precise, short. No hype. Do not pretend an action already happened unless autonomy is act and the action is low risk — even then, describe it as proposed for the workspace to apply.",
      "Use only the supplied memories, knowledge, tasks, and projects. If you do not know, say so.",
      "Never invent memories. Never claim to control a computer, phone, email, or home.",
      "This workspace stores data in the owner's browser. Do not ask them to paste secrets.",
      "Return ONLY JSON with this shape:",
      '{"text":"reply","actions":[]}',
      "Action objects:",
      '{"type":"remember","title":"","body":"","kind":"fact|preference|person|note"}',
      '{"type":"task","title":"","due":"optional short date"}',
      '{"type":"knowledge","title":"","body":""}',
      '{"type":"forget","title":"exact memory title"}',
      "Propose an action only when the owner asked to remember, schedule, file, or forget, or stated a durable fact about themselves.",
      "If emergencyStop is true, actions must be an empty array.",
      "Keep text under 160 words. When you use a memory, name its title.",
    ].join("\n");

    const requestBody = {
      model: "grok-4.5",
      temperature: 0.4,
      max_tokens: 700,
      messages: [
        { role: "system", content: system },
        {
          role: "system",
          content: `Workspace context:\n${JSON.stringify(context)}`,
        },
        ...data.messages,
      ],
    };

    try {
      let res = await complete(apiKey, requestBody);
      if (res.status === 429 || res.status >= 500) {
        res = await complete(apiKey, requestBody);
      }
      if (!res.ok) return { ok: false, error: `Cloud mind error ${res.status}` };
      const json = (await res.json()) as {
        choices?: { message?: { content?: string } }[];
      };
      const raw = json.choices?.[0]?.message?.content ?? "";
      if (!raw.trim()) return { ok: false, error: "Cloud mind returned an empty reply" };
      const parsed = parseModel(raw);
      return {
        ok: true,
        text: parsed.text,
        actions: data.emergency ? [] : parsed.actions,
        model: "grok-4.5",
      };
    } catch {
      return { ok: false, error: "Cloud mind did not respond" };
    }
  });
