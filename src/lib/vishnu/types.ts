export type Autonomy = "observe" | "suggest" | "ask" | "act";
export type DataPolicy = "device_only";
export type MemoryKind = "fact" | "preference" | "person" | "note";
export type View =
  | "home"
  | "memory"
  | "graph"
  | "tree"
  | "knowledge"
  | "today"
  | "projects"
  | "inbox"
  | "live"
  | "workflows"
  | "apps"
  | "agents"
  | "activity"
  | "devices"
  | "companion"
  | "desktop"
  | "vault"
  | "sensorium"
  | "system"
  | "settings"
  | "products"
  | "storage"
  | "voice"
  | "dashboard"
  | "approvals"
  | "notifications"
  | "models"
  | "relationships"
  | "extensions";

export type Proposal =
  | { type: "remember"; title: string; body: string; kind: MemoryKind; risk: "low" }
  | { type: "task"; title: string; due?: string; risk: "low" }
  | { type: "knowledge"; title: string; body: string; risk: "low" }
  | { type: "forget"; title: string; risk: "consequential" };

export type ActionStatus = "pending" | "applied" | "dismissed";

export type ChatAction = {
  id: string;
  proposal: Proposal;
  status: ActionStatus;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  actions?: ChatAction[];
  source?: "model" | "local";
};

export type Conversation = {
  id: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
};

export type MemoryItem = {
  id: string;
  title: string;
  body: string;
  kind: MemoryKind;
  sensitive: boolean;
  createdAt: string;
  updatedAt: string;
};

export type KnowledgeItem = {
  id: string;
  title: string;
  body: string;
  createdAt: string;
};

export type TaskItem = {
  id: string;
  title: string;
  due?: string;
  done: boolean;
  createdAt: string;
};

export type ProjectItem = {
  id: string;
  title: string;
  intent: string;
  next: string;
  status: "idea" | "active" | "paused" | "done";
  createdAt: string;
};

export type Routine = {
  id: string;
  title: string;
  prompt: string;
};

export type DeviceItem = {
  id: string;
  name: string;
  kind: "browser" | "phone" | "desktop" | "other";
  code: string;
  pairedAt: string;
  lastSeen: string;
  revoked: boolean;
  connected: boolean;
  scopes: string[];
};

export type ActivityItem = {
  id: string;
  at: string;
  kind: string;
  detail: string;
};

export type Owner = {
  name: string;
  createdAt: string;
  recoveryCodes: string[];
};

export type Settings = {
  autonomy: Autonomy;
  voice: boolean;
  emergency: boolean;
  includeSensitive: boolean;
  model: "cloud" | "local";
  storageSync: boolean;
  voiceRate: number;
  voicePitch: number;
};

export type ProductItem = {
  id: string;
  name: string;
  audience: string;
  promise: string;
  sourceProjectId?: string;
  createdAt: string;
};

export type ExtensionItem = {
  id: string;
  name: string;
  note: string;
  enabled: boolean;
};

export type AskPayload = {
  ownerName: string;
  autonomy: Autonomy;
  emergency: boolean;
  messages: { role: "user" | "assistant"; content: string }[];
  memories: { title: string; body: string; kind: string }[];
  knowledge: { title: string; excerpt: string }[];
  tasks: { title: string; done: boolean; due?: string }[];
  projects: { title: string; status: string; next: string }[];
};

export type AskResult =
  | { ok: true; text: string; actions: Proposal[]; model: string }
  | { ok: false; error: string };

export type MemoryLink = {
  id: string;
  fromId: string;
  toId: string;
  label: string;
};

export type InboxItem = {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  read: boolean;
};

export type LiveJob = {
  id: string;
  title: string;
  detail: string;
  status: "running" | "paused" | "done" | "failed";
  progress: number;
  updatedAt: string;
};

export type WorkflowItem = {
  id: string;
  name: string;
  steps: string[];
  enabled: boolean;
  lastRun?: string;
};

export type AutomationItem = {
  id: string;
  name: string;
  when: string;
  action: string;
  enabled: boolean;
};

export type AgentItem = {
  id: string;
  name: string;
  mandate: string;
  status: "idle" | "working" | "blocked";
};

export type CapabilityItem = {
  id: string;
  name: string;
  kind: "built-in" | "app" | "mcp" | "openapi";
  risk: "low" | "high";
  connected: boolean;
  detail: string;
};

export type VaultBlob = {
  salt: string;
  iv: string;
  ciphertext: string;
  updatedAt: string;
};

export type SensoriumState = {
  microphone: boolean;
  screen: boolean;
  location: boolean;
  notifications: boolean;
  stopped: boolean;
};
