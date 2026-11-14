import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type {
  ActivityItem,
  AgentItem,
  AutomationItem,
  Autonomy,
  CapabilityItem,
  ChatMessage,
  Conversation,
  DeviceItem,
  InboxItem,
  KnowledgeItem,
  LiveJob,
  MemoryItem,
  MemoryKind,
  MemoryLink,
  Owner,
  ProjectItem,
  Proposal,
  ProductItem,
  ExtensionItem,
  Routine,
  SensoriumState,
  Settings,
  TaskItem,
  VaultBlob,
  View,
  WorkflowItem,
} from "./types";

export type VishnuData = {
  owner: Owner | null;
  view: View;
  conversations: Conversation[];
  activeId: string | null;
  memories: MemoryItem[];
  knowledge: KnowledgeItem[];
  tasks: TaskItem[];
  projects: ProjectItem[];
  routines: Routine[];
  devices: DeviceItem[];
  links: MemoryLink[];
  inbox: InboxItem[];
  jobs: LiveJob[];
  workflows: WorkflowItem[];
  automations: AutomationItem[];
  agents: AgentItem[];
  capabilities: CapabilityItem[];
  vault: VaultBlob | null;
  sensorium: SensoriumState;
  activity: ActivityItem[];
  settings: Settings;
  products: ProductItem[];
  extensions: ExtensionItem[];
  dismissedNotices: string[];
  composerDraft: string;
};

type VishnuState = VishnuData & {
  setView: (view: View) => void;
  setDraft: (draft: string) => void;
  completeSetup: (owner: Owner, autonomy: Autonomy) => void;
  setAutonomy: (autonomy: Autonomy) => void;
  setVoice: (voice: boolean) => void;
  setEmergency: (emergency: boolean) => void;
  setIncludeSensitive: (include: boolean) => void;
  newChat: () => string;
  openChat: (id: string) => void;
  deleteChat: (id: string) => void;
  appendMessage: (conversationId: string, message: ChatMessage) => void;
  setActionStatus: (
    conversationId: string,
    messageId: string,
    actionId: string,
    status: "applied" | "dismissed",
  ) => void;
  applyProposal: (proposal: Proposal) => string;
  addMemory: (input: { title: string; body: string; kind: MemoryKind; sensitive?: boolean }) => void;
  updateMemory: (id: string, patch: Partial<Pick<MemoryItem, "title" | "body" | "kind" | "sensitive">>) => void;
  deleteMemory: (id: string) => void;
  addKnowledge: (input: { title: string; body: string }) => void;
  deleteKnowledge: (id: string) => void;
  addTask: (title: string, due?: string) => void;
  toggleTask: (id: string) => void;
  deleteTask: (id: string) => void;
  addProject: (input: { title: string; intent: string; next: string }) => void;
  updateProject: (id: string, patch: Partial<Pick<ProjectItem, "status" | "next" | "intent" | "title">>) => void;
  deleteProject: (id: string) => void;
  addDevice: (input: { name: string; kind: DeviceItem["kind"] }) => DeviceItem;
  revokeDevice: (id: string) => void;
  redeemCode: (code: string) => string;
  touchBrowser: () => void;
  linkMemories: (fromId: string, toId: string, label: string) => void;
  unlink: (id: string) => void;
  addInbox: (title: string, body: string) => void;
  toggleInbox: (id: string) => void;
  addWorkflow: (name: string, steps: string) => void;
  toggleWorkflow: (id: string) => void;
  runWorkflow: (id: string) => void;
  addAutomation: (name: string, when: string, action: string) => void;
  toggleAutomation: (id: string) => void;
  runAutomations: (text: string) => void;
  setAgentStatus: (id: string, status: AgentItem["status"]) => void;
  briefAgent: (id: string, goal: string) => void;
  addAgent: (name: string, mandate: string) => void;
  toggleCapability: (id: string) => void;
  addProduct: (input: { name: string; audience: string; promise: string; sourceProjectId?: string }) => void;
  deleteProduct: (id: string) => void;
  addExtension: (name: string, note: string) => void;
  toggleExtension: (id: string) => void;
  dismissNotice: (id: string) => void;
  setModel: (model: Settings["model"]) => void;
  setStorageSync: (on: boolean) => void;
  setVoiceRate: (rate: number) => void;
  setVoicePitch: (pitch: number) => void;
  setVault: (vault: VaultBlob | null) => void;
  setSensor: (patch: Partial<SensoriumState>) => void;
  stopSensing: () => void;
  log: (kind: string, detail: string) => void;
  importData: (data: Partial<VishnuData>) => void;
  hydrateFromServer: (data: Partial<VishnuData>) => void;
  resetWorkspace: () => void;
  syncState: "loading" | "ready" | "offline";
  setSyncState: (state: "loading" | "ready" | "offline") => void;
};

const emptySettings: Settings = {
  autonomy: "ask",
  voice: false,
  emergency: false,
  includeSensitive: false,
  model: "cloud",
  storageSync: true,
  voiceRate: 1,
  voicePitch: 1,
};

function uid(prefix: string) {
  return `${prefix}_${crypto.randomUUID()}`;
}

export function pairingCode() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let s = "";
  for (const b of bytes) s += alphabet[b % alphabet.length];
  return `VISHNU-${s.slice(0, 4)}-${s.slice(4)}`;
}

function now() {
  return new Date().toISOString();
}

const defaultSensor = (): SensoriumState => ({
  microphone: false,
  screen: false,
  location: false,
  notifications: false,
  stopped: false,
});

const defaultCapabilities = (): CapabilityItem[] => [
  { id: "cap_notes", name: "Notes", kind: "built-in", risk: "low", connected: true, detail: "File text into Knowledge." },
  { id: "cap_files", name: "Documents", kind: "built-in", risk: "low", connected: true, detail: "Read PDF, Word, and spreadsheets in the browser." },
  { id: "cap_search", name: "Web search link", kind: "built-in", risk: "low", connected: false, detail: "Opens a search URL. Does not browse by itself." },
  { id: "cap_mail", name: "Mail", kind: "app", risk: "high", connected: false, detail: "Not connected. Sending mail is not available from this workspace." },
  { id: "cap_calendar", name: "Calendar", kind: "app", risk: "high", connected: false, detail: "Not connected. No calendar writes are sent." },
  { id: "cap_mcp", name: "MCP tools", kind: "mcp", risk: "high", connected: false, detail: "No MCP server is attached." },
];

function blankData(): VishnuData {
  return {
    owner: null,
    view: "home",
    conversations: [],
    activeId: null,
    memories: [],
    knowledge: [],
    tasks: [],
    projects: [],
    routines: [],
    devices: [],
    links: [],
    inbox: [],
    jobs: [],
    workflows: [],
    automations: [],
    agents: [],
    capabilities: defaultCapabilities(),
    vault: null,
    sensorium: defaultSensor(),
    activity: [],
    settings: emptySettings,
    products: [],
    extensions: [],
    dismissedNotices: [],
    composerDraft: "",
  };
}

function clipActivity(items: ActivityItem[]) {
  return items.slice(0, 200);
}

function fillDoc(data: Partial<VishnuData>): VishnuData {
  const base = blankData();
  return {
    ...base,
    ...data,
    settings: { ...emptySettings, ...data.settings },
    sensorium: { ...defaultSensor(), ...data.sensorium },
    capabilities: data.capabilities?.length ? data.capabilities : base.capabilities,
    products: data.products ?? [],
    extensions: data.extensions ?? [],
    dismissedNotices: data.dismissedNotices ?? [],
    links: data.links ?? [],
    inbox: data.inbox ?? [],
    jobs: data.jobs ?? [],
    workflows: data.workflows ?? [],
    automations: data.automations ?? [],
    agents: data.agents ?? [],
    devices: (data.devices ?? []).map((d) => ({ ...d, connected: d.connected !== false && !d.revoked })),
    composerDraft: "",
  };
}

export const useVishnu = create<VishnuState>()(
  persist(
    (set, get) => ({
      ...blankData(),
      syncState: "loading",
      setSyncState: (syncState) => set({ syncState }),
      setView: (view) => set({ view }),
      setDraft: (composerDraft) => set({ composerDraft }),
      completeSetup: (owner, autonomy) => {
        const at = now();
        const conversationId = uid("chat");
        const device: DeviceItem = {
          id: uid("dev"),
          name: "This browser",
          kind: "browser",
          code: pairingCode(),
          pairedAt: at,
          lastSeen: at,
          revoked: false,
          connected: true,
          scopes: ["talk", "memory", "knowledge", "tasks"],
        };
        set({
          owner,
          settings: { ...emptySettings, autonomy },
          devices: [device],
          conversations: [{ id: conversationId, title: "New conversation", updatedAt: at, messages: [] }],
          activeId: conversationId,
          routines: [
            {
              id: uid("rt"),
              title: "Morning brief",
              prompt:
                "Look at my open tasks, projects, and memories. Tell me the three things that matter today. Do not create anything unless I ask.",
            },
            {
              id: uid("rt"),
              title: "Weekly review",
              prompt: "Summarize my active projects, unfinished tasks, and anything in memory that still needs a decision.",
            },
          ],
          workflows: [
            {
              id: uid("wf"),
              name: "Capture a decision",
              steps: ["inbox:A decision needs a look", "task:Write the decision down"],
              enabled: true,
            },
          ],
          automations: [
            {
              id: uid("au"),
              name: "Flag a keep",
              when: "please keep",
              action: "inbox:You asked to keep something",
              enabled: false,
            },
          ],
          agents: [
            {
              id: uid("ag"),
              name: "Planner",
              mandate: "Turn a goal into ordered steps. Do not act on the world.",
              status: "idle",
            },
          ],
          capabilities: defaultCapabilities(),
          activity: [
            {
              id: uid("act"),
              at,
              kind: "setup",
              detail: `Workspace created for ${owner.name}. It syncs with this signed-in account.`,
            },
          ],
          view: "home",
        });
      },
      setAutonomy: (autonomy) => set((s) => ({ settings: { ...s.settings, autonomy } })),
      setVoice: (voice) => set((s) => ({ settings: { ...s.settings, voice } })),
      setEmergency: (emergency) => {
        set((s) => ({ settings: { ...s.settings, emergency } }));
        get().log("security", emergency ? "Emergency stop engaged" : "Emergency stop lifted");
      },
      setIncludeSensitive: (includeSensitive) =>
        set((s) => ({ settings: { ...s.settings, includeSensitive } })),
      newChat: () => {
        const id = uid("chat");
        const at = now();
        set((s) => ({
          conversations: [{ id, title: "New conversation", updatedAt: at, messages: [] }, ...s.conversations].slice(0, 40),
          activeId: id,
          view: "home",
          composerDraft: "",
        }));
        return id;
      },
      openChat: (id) => set({ activeId: id, view: "home" }),
      deleteChat: (id) =>
        set((s) => {
          const conversations = s.conversations.filter((c) => c.id !== id);
          return { conversations, activeId: s.activeId === id ? (conversations[0]?.id ?? null) : s.activeId };
        }),
      appendMessage: (conversationId, message) =>
        set((s) => ({
          conversations: s.conversations.map((c) => {
            if (c.id !== conversationId) return c;
            const messages = [...c.messages, message].slice(-200);
            const title =
              c.title === "New conversation" && message.role === "user"
                ? message.content.replace(/\s+/g, " ").slice(0, 52)
                : c.title;
            return { ...c, title, messages, updatedAt: message.createdAt };
          }),
        })),
      setActionStatus: (conversationId, messageId, actionId, status) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id !== conversationId
              ? c
              : {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id !== messageId
                      ? m
                      : { ...m, actions: m.actions?.map((a) => (a.id === actionId ? { ...a, status } : a)) },
                  ),
                },
          ),
        })),
      applyProposal: (proposal) => {
        if (proposal.type === "remember") {
          get().addMemory({ title: proposal.title, body: proposal.body, kind: proposal.kind });
          return `Saved memory “${proposal.title}”.`;
        }
        if (proposal.type === "task") {
          get().addTask(proposal.title, proposal.due);
          return `Added task “${proposal.title}”.`;
        }
        if (proposal.type === "knowledge") {
          get().addKnowledge({ title: proposal.title, body: proposal.body });
          return `Filed knowledge “${proposal.title}”.`;
        }
        const hit = get().memories.find((m) => m.title.toLowerCase() === proposal.title.toLowerCase());
        if (!hit) return `No memory titled “${proposal.title}”.`;
        get().deleteMemory(hit.id);
        return `Forgot “${hit.title}”.`;
      },
      addMemory: (input) => {
        const at = now();
        const item: MemoryItem = {
          id: uid("mem"),
          title: input.title.trim().slice(0, 120),
          body: input.body.trim().slice(0, 2000),
          kind: input.kind,
          sensitive: Boolean(input.sensitive),
          createdAt: at,
          updatedAt: at,
        };
        set((s) => ({ memories: [item, ...s.memories].slice(0, 400) }));
        get().log("memory", `Remembered “${item.title}”.`);
      },
      updateMemory: (id, patch) =>
        set((s) => ({
          memories: s.memories.map((m) => (m.id === id ? { ...m, ...patch, updatedAt: now() } : m)),
        })),
      deleteMemory: (id) => {
        const item = get().memories.find((m) => m.id === id);
        set((s) => ({
          memories: s.memories.filter((m) => m.id !== id),
          links: s.links.filter((l) => l.fromId !== id && l.toId !== id),
        }));
        if (item) get().log("memory", `Deleted memory “${item.title}”.`);
      },
      addKnowledge: (input) => {
        const item: KnowledgeItem = {
          id: uid("know"),
          title: input.title.trim().slice(0, 140) || "Untitled note",
          body: input.body.trim().slice(0, 20000),
          createdAt: now(),
        };
        set((s) => ({ knowledge: [item, ...s.knowledge].slice(0, 200) }));
        get().log("knowledge", `Added source “${item.title}”.`);
      },
      deleteKnowledge: (id) => {
        const item = get().knowledge.find((k) => k.id === id);
        set((s) => ({ knowledge: s.knowledge.filter((k) => k.id !== id) }));
        if (item) get().log("knowledge", `Removed source “${item.title}”.`);
      },
      addTask: (title, due) => {
        const clean = title.trim().slice(0, 180);
        if (!clean) return;
        set((s) => ({
          tasks: [{ id: uid("task"), title: clean, due: due?.trim() || undefined, done: false, createdAt: now() }, ...s.tasks].slice(0, 200),
        }));
        get().log("task", `Task added: ${clean}`);
      },
      toggleTask: (id) => set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? { ...t, done: !t.done } : t)) })),
      deleteTask: (id) => set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) })),
      addProject: (input) => {
        const item: ProjectItem = {
          id: uid("prj"),
          title: input.title.trim().slice(0, 120),
          intent: input.intent.trim().slice(0, 500),
          next: input.next.trim().slice(0, 200),
          status: "active",
          createdAt: now(),
        };
        if (!item.title) return;
        set((s) => ({ projects: [item, ...s.projects].slice(0, 80) }));
        get().log("project", `Project opened: ${item.title}`);
      },
      updateProject: (id, patch) =>
        set((s) => ({ projects: s.projects.map((p) => (p.id === id ? { ...p, ...patch } : p)) })),
      deleteProject: (id) => set((s) => ({ projects: s.projects.filter((p) => p.id !== id) })),
      addDevice: (input) => {
        const at = now();
        const device: DeviceItem = {
          id: uid("dev"),
          name: input.name.trim().slice(0, 60) || "Unnamed device",
          kind: input.kind,
          code: pairingCode(),
          pairedAt: at,
          lastSeen: at,
          revoked: false,
          connected: false,
          scopes: ["talk"],
        };
        set((s) => ({ devices: [device, ...s.devices] }));
        get().log("device", `Pairing code ready for ${device.name}. Enter it on the companion to connect.`);
        return device;
      },
      revokeDevice: (id) => {
        const device = get().devices.find((d) => d.id === id);
        set((s) => ({
          devices: s.devices.map((d) => (d.id === id ? { ...d, revoked: true, connected: false } : d)),
        }));
        if (device) get().log("device", `Revoked ${device.name}.`);
      },
      redeemCode: (code) => {
        const clean = code.trim().toLowerCase();
        const hit = get().devices.find((d) => d.code.toLowerCase() === clean && !d.revoked);
        if (!hit) return "No device is waiting for that code.";
        set((s) => ({
          devices: s.devices.map((d) => (d.id === hit.id ? { ...d, connected: true, lastSeen: now() } : d)),
        }));
        get().log("device", `Connected ${hit.name}.`);
        return `Connected ${hit.name}.`;
      },
      touchBrowser: () =>
        set((s) => ({
          devices: s.devices.map((d) =>
            d.kind === "browser" && d.name === "This browser" && !d.revoked
              ? { ...d, connected: true, lastSeen: now() }
              : d,
          ),
        })),
      linkMemories: (fromId, toId, label) => {
        if (!fromId || !toId || fromId === toId) return;
        set((s) => ({
          links: [{ id: uid("lnk"), fromId, toId, label: label.trim().slice(0, 40) || "related" }, ...s.links].slice(0, 200),
        }));
        get().log("memory", "Linked two memories.");
      },
      unlink: (id) => set((s) => ({ links: s.links.filter((l) => l.id !== id) })),
      addInbox: (title, body) => {
        set((s) => ({
          inbox: [
            {
              id: uid("in"),
              title: title.trim().slice(0, 140) || "Notice",
              body: body.trim().slice(0, 2000),
              createdAt: now(),
              read: false,
            },
            ...s.inbox,
          ].slice(0, 100),
        }));
      },
      toggleInbox: (id) =>
        set((s) => ({ inbox: s.inbox.map((item) => (item.id === id ? { ...item, read: !item.read } : item)) })),
      addWorkflow: (name, steps) => {
        const parsed = steps.split("\n").map((line) => line.trim()).filter(Boolean).slice(0, 8);
        if (!name.trim() || !parsed.length) return;
        set((s) => ({
          workflows: [{ id: uid("wf"), name: name.trim().slice(0, 80), steps: parsed, enabled: true }, ...s.workflows],
        }));
      },
      toggleWorkflow: (id) =>
        set((s) => ({ workflows: s.workflows.map((w) => (w.id === id ? { ...w, enabled: !w.enabled } : w)) })),
      runWorkflow: (id) => {
        const wf = get().workflows.find((w) => w.id === id);
        if (!wf || !wf.enabled) return;
        const jobId = uid("job");
        const at = now();
        const job: LiveJob = {
          id: jobId,
          title: wf.name,
          detail: "Running steps",
          status: "running",
          progress: 20,
          updatedAt: at,
        };
        set((s) => ({
          jobs: [job, ...s.jobs].slice(0, 40),
          workflows: s.workflows.map((w) => (w.id === id ? { ...w, lastRun: at } : w)),
        }));
        for (const step of wf.steps) {
          const [kind, ...rest] = step.split(":");
          const text = rest.join(":").trim() || step;
          if (kind === "task") get().addTask(text);
          else get().addInbox(text, wf.name);
        }
        set((s) => ({
          jobs: s.jobs.map((job) =>
            job.id === jobId ? { ...job, status: "done", progress: 100, detail: "Steps applied", updatedAt: now() } : job,
          ),
        }));
        get().log("workflow", `Ran ${wf.name}.`);
      },
      addAutomation: (name, when, action) => {
        if (!name.trim() || !when.trim() || !action.trim()) return;
        set((s) => ({
          automations: [
            {
              id: uid("au"),
              name: name.trim().slice(0, 80),
              when: when.trim().slice(0, 80),
              action: action.trim().slice(0, 160),
              enabled: true,
            },
            ...s.automations,
          ],
        }));
      },
      toggleAutomation: (id) =>
        set((s) => ({ automations: s.automations.map((a) => (a.id === id ? { ...a, enabled: !a.enabled } : a)) })),
      runAutomations: (text) => {
        const lower = text.toLowerCase();
        for (const rule of get().automations) {
          if (!rule.enabled || !rule.when || !lower.includes(rule.when.toLowerCase())) continue;
          const [kind, ...rest] = rule.action.split(":");
          const body = rest.join(":").trim() || rule.name;
          if (kind === "task") get().addTask(body);
          else if (kind === "remember") get().addMemory({ title: body.slice(0, 80), body, kind: "note" });
          else get().addInbox(body, rule.name);
          get().log("automation", `Ran “${rule.name}”.`);
        }
      },
      setAgentStatus: (id, status) =>
        set((s) => ({ agents: s.agents.map((a) => (a.id === id ? { ...a, status } : a)) })),
      briefAgent: (id, goal) => {
        const agent = get().agents.find((a) => a.id === id);
        if (!agent || !goal.trim()) return;
        const steps = goal.split(/[.\n]/).map((part) => part.trim()).filter((part) => part.length > 2).slice(0, 6);
        const detail = steps.map((step, i) => `${i + 1}. ${step}`).join("\n") || goal.trim();
        const job: LiveJob = {
          id: uid("job"),
          title: `${agent.name}: ${goal.trim().slice(0, 80)}`,
          detail,
          status: "done",
          progress: 100,
          updatedAt: now(),
        };
        set((s) => ({
          jobs: [job, ...s.jobs].slice(0, 40),
          agents: s.agents.map((a) => (a.id === id ? { ...a, status: "idle" } : a)),
        }));
        get().addInbox(`${agent.name} filed a plan`, detail);
        get().log("agent", `${agent.name} planned work. It did not act.`);
      },
      addAgent: (name, mandate) => {
        const clean = name.trim().slice(0, 60);
        if (!clean) return;
        const agentItem: AgentItem = {
          id: uid("ag"),
          name: clean,
          mandate: mandate.trim().slice(0, 280) || "Plan only. Do not act on the world.",
          status: "idle",
        };
        set((s) => ({
          agents: [agentItem, ...s.agents].slice(0, 12),
        }));
        get().log("agent", `Added agent ${clean}.`);
      },
      toggleCapability: (id) => {
        const cap = get().capabilities.find((c) => c.id === id);
        if (!cap) return;
        set((s) => ({
          capabilities: s.capabilities.map((c) => (c.id === id ? { ...c, connected: !c.connected } : c)),
        }));
        get().log("capability", `${cap.connected ? "Disconnected" : "Connected"} ${cap.name}.`);
      },
      addProduct: (input) => {
        const name = input.name.trim().slice(0, 80);
        if (!name) return;
        const product: ProductItem = {
          id: uid("prod"),
          name,
          audience: input.audience.trim().slice(0, 120),
          promise: input.promise.trim().slice(0, 400),
          ...(input.sourceProjectId ? { sourceProjectId: input.sourceProjectId } : {}),
          createdAt: now(),
        };
        set((s) => ({ products: [product, ...s.products].slice(0, 40) }));
        get().log("product", `Created product ${name}.`);
      },
      deleteProduct: (id) => {
        const hit = get().products.find((p) => p.id === id);
        set((s) => ({ products: s.products.filter((p) => p.id !== id) }));
        if (hit) get().log("product", `Removed product ${hit.name}.`);
      },
      addExtension: (name, note) => {
        const clean = name.trim().slice(0, 60);
        if (!clean) return;
        const item: ExtensionItem = {
          id: uid("ext"),
          name: clean,
          note: note.trim().slice(0, 200) || "Recorded only. It does not run outside code.",
          enabled: false,
        };
        set((s) => ({ extensions: [item, ...s.extensions].slice(0, 30) }));
        get().log("extension", `Recorded extension ${clean}. It is not loaded as code.`);
      },
      toggleExtension: (id) => {
        set((s) => ({
          extensions: s.extensions.map((item) => (item.id === id ? { ...item, enabled: !item.enabled } : item)),
        }));
      },
      dismissNotice: (id) => set((s) => ({ dismissedNotices: [...s.dismissedNotices, id].slice(-200) })),
      setModel: (model) => {
        set((s) => ({ settings: { ...s.settings, model } }));
        get().log("model", model === "local" ? "Answers stay on the local brain." : "Answers may use the cloud mind.");
      },
      setStorageSync: (storageSync) => {
        set((s) => ({ settings: { ...s.settings, storageSync } }));
        get().log("storage", storageSync ? "Account sync is on." : "New changes stay in this browser.");
      },
      setVoiceRate: (voiceRate) => set((s) => ({ settings: { ...s.settings, voiceRate } })),
      setVoicePitch: (voicePitch) => set((s) => ({ settings: { ...s.settings, voicePitch } })),
      setVault: (vault) => set({ vault }),
      setSensor: (patch) => set((s) => ({ sensorium: { ...s.sensorium, ...patch, stopped: false } })),
      stopSensing: () => {
        set({ sensorium: { microphone: false, screen: false, location: false, notifications: false, stopped: true } });
        get().log("sensorium", "Stopped all sensing.");
      },
      log: (kind, detail) =>
        set((s) => ({
          activity: clipActivity([{ id: uid("act"), at: now(), kind, detail }, ...s.activity]),
        })),
      importData: (data) => {
        set({ ...fillDoc(data), view: "home" });
        get().log("data", "Workspace restored.");
      },
      hydrateFromServer: (data) => set(fillDoc(data)),
      resetWorkspace: () => set(blankData()),
    }),
    {
      name: "vishnu-workspace-v1",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => workspaceSnapshot(s),
      merge: (persisted, current) => ({
        ...current,
        ...fillDoc((persisted ?? {}) as Partial<VishnuData>),
      }),
    },
  ),
);

export function workspaceSnapshot(data: VishnuData) {
  return {
    owner: data.owner,
    view: data.view,
    conversations: data.conversations,
    activeId: data.activeId,
    memories: data.memories,
    knowledge: data.knowledge,
    tasks: data.tasks,
    projects: data.projects,
    routines: data.routines,
    devices: data.devices,
    links: data.links,
    inbox: data.inbox,
    jobs: data.jobs,
    workflows: data.workflows,
    automations: data.automations,
    agents: data.agents,
    capabilities: data.capabilities,
    products: data.products,
    extensions: data.extensions,
    dismissedNotices: data.dismissedNotices,
    vault: data.vault,
    sensorium: data.sensorium,
    activity: data.activity,
    settings: data.settings,
  };
}

export function activeConversation(data: VishnuData): Conversation | null {
  return data.conversations.find((c) => c.id === data.activeId) ?? data.conversations[0] ?? null;
}
