import type { VishnuData } from "./store";
import type { AskPayload, Proposal } from "./types";

function terms(text: string) {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 2 && !STOP.has(t));
}

const STOP = new Set([
  "the",
  "and",
  "for",
  "you",
  "your",
  "that",
  "this",
  "with",
  "what",
  "about",
  "have",
  "from",
  "are",
  "was",
  "were",
  "can",
  "please",
  "today",
  "vishnu",
]);

function score(query: string, text: string) {
  const needles = terms(query);
  if (!needles.length) return 0;
  const hay = text.toLowerCase();
  return needles.reduce((n, t) => n + (hay.includes(t) ? 1 : 0), 0);
}

export function buildPayload(data: VishnuData, history: { role: "user" | "assistant"; content: string }[]): AskPayload {
  const query = history.filter((m) => m.role === "user").slice(-1)[0]?.content ?? "";
  const allowSensitive = data.settings.includeSensitive;
  const memories = data.memories
    .filter((m) => allowSensitive || !m.sensitive)
    .map((m) => ({ m, s: score(query, `${m.title} ${m.body}`) }))
    .sort((a, b) => b.s - a.s || b.m.updatedAt.localeCompare(a.m.updatedAt))
    .slice(0, 10)
    .map(({ m }) => ({ title: m.title, body: m.body.slice(0, 500), kind: m.kind }));

  const knowledge = data.knowledge
    .map((k) => ({ k, s: score(query, `${k.title} ${k.body}`) }))
    .sort((a, b) => b.s - a.s || b.k.createdAt.localeCompare(a.k.createdAt))
    .slice(0, 6)
    .map(({ k }) => ({ title: k.title, excerpt: k.body.slice(0, 400) }));

  return {
    ownerName: data.owner?.name ?? "Owner",
    autonomy: data.settings.autonomy,
    emergency: data.settings.emergency,
    messages: history.slice(-12).map((m) => ({
      role: m.role,
      content: m.content.slice(0, 4000),
    })),
    memories,
    knowledge,
    tasks: data.tasks
      .filter((t) => !t.done)
      .slice(0, 12)
      .map((t) => ({ title: t.title, done: t.done, due: t.due })),
    projects: data.projects.slice(0, 8).map((p) => ({
      title: p.title,
      status: p.status,
      next: p.next,
    })),
  };
}

function rememberFrom(text: string): Proposal | null {
  const m = text.match(/^(?:please\s+)?remember(?:\s+that)?\s+(.+)$/i);
  if (!m) return null;
  const body = m[1].trim();
  const title = body.split(/[.—]/)[0]?.trim().slice(0, 80) || "Note";
  return { type: "remember", title, body, kind: "fact", risk: "low" };
}

function taskFrom(text: string): Proposal | null {
  const m = text.match(/^(?:please\s+)?remind me(?:\s+to)?\s+(.+)$/i);
  if (!m) return null;
  return { type: "task", title: m[1].trim().slice(0, 180), risk: "low" };
}

function noteFrom(text: string): Proposal | null {
  const m = text.match(/^(?:please\s+)?(?:save a note|note|file this)\s*[:—-]?\s+(.+)$/is);
  if (!m) return null;
  const body = m[1].trim();
  const title = body.split("\n")[0]?.slice(0, 80) || "Note";
  return { type: "knowledge", title, body, risk: "low" };
}

export function localAnswer(data: VishnuData, input: string): { text: string; actions: Proposal[] } {
  const q = input.trim();
  const lower = q.toLowerCase();

  if (data.settings.emergency && /remember|remind|save a note|forget|file this/i.test(q)) {
    return {
      text: "Emergency stop is on. I will not write memory, tasks, or knowledge until you lift it in Settings.",
      actions: [],
    };
  }

  const proposal = rememberFrom(q) || taskFrom(q) || noteFrom(q);
  if (proposal) {
    const label =
      proposal.type === "remember"
        ? `I can remember “${proposal.title}”.`
        : proposal.type === "task"
          ? `I can add “${proposal.title}” to Today.`
          : `I can file “${proposal.title}” under Knowledge.`;
    return {
      text:
        data.settings.autonomy === "act" && proposal.risk === "low"
          ? label.replace("I can ", "I will ")
          : `${label} Confirm it below if you want it kept.`,
      actions: [proposal],
    };
  }

  if (/forget\s+/.test(lower)) {
    const title = q.replace(/^.*forget\s+/i, "").replace(/[."]+$/g, "").trim();
    return {
      text: title
        ? `Forgetting is consequential. Confirm if “${title}” should be removed.`
        : "Tell me the memory title to forget.",
      actions: title ? [{ type: "forget", title, risk: "consequential" }] : [],
    };
  }

  if (/what do you remember|show memories|my memories/.test(lower)) {
    const list = data.memories.slice(0, 8);
    if (!list.length) return { text: "I don’t have any memories yet. Say “Remember that …” to keep one.", actions: [] };
    return {
      text: `Here is what I am holding:\n${list.map((m) => `• ${m.title} — ${m.body}`).join("\n")}`,
      actions: [],
    };
  }

  if (/open tasks|what'?s today|whats today|my tasks|today/.test(lower) && data.tasks.length) {
    const open = data.tasks.filter((t) => !t.done);
    if (!open.length) return { text: "Today is clear. No open tasks.", actions: [] };
    return {
      text: `Open tasks:\n${open.map((t) => `• ${t.title}${t.due ? ` (${t.due})` : ""}`).join("\n")}`,
      actions: [],
    };
  }

  const hits = [
    ...data.memories
      .filter((m) => data.settings.includeSensitive || !m.sensitive)
      .map((m) => ({ kind: "Memory", title: m.title, body: m.body, s: score(q, `${m.title} ${m.body}`) })),
    ...data.knowledge.map((k) => ({
      kind: "Knowledge",
      title: k.title,
      body: k.body.slice(0, 280),
      s: score(q, `${k.title} ${k.body}`),
    })),
    ...data.projects.map((p) => ({
      kind: "Project",
      title: p.title,
      body: `${p.status}. Next: ${p.next || "unset"}. ${p.intent}`,
      s: score(q, `${p.title} ${p.intent} ${p.next}`),
    })),
  ]
    .filter((h) => h.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, 4);

  if (hits.length) {
    return {
      text: `From this device:\n${hits.map((h) => `• ${h.kind}: ${h.title} — ${h.body}`).join("\n")}`,
      actions: [],
    };
  }

  return {
    text: "The cloud mind is offline, so I stayed on this device. I can still remember, remind, and file notes. Try “Remember that …”, “Remind me to …”, or “Save a note: …”. Ask again when the cloud mind is connected for open-ended reasoning.",
    actions: [],
  };
}

export function shouldAutoApply(autonomy: VishnuData["settings"]["autonomy"], proposal: Proposal, emergency: boolean) {
  if (emergency) return false;
  if (proposal.risk === "consequential") return false;
  return autonomy === "act";
}
