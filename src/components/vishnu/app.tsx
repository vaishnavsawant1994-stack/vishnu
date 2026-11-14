import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  Brain,
  Ellipsis,
  FolderKanban,
  Inbox,
  Library,
  MessageCircle,
  Monitor,
  Network,
  Search,
  Settings,
  Shield,
  Smartphone,
  Sun,
  Workflow,
  X,
} from "lucide-react";
import { UserButton } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import { aiAvailable } from "@/lib/vishnu/ask";
import { toast } from "sonner";
import { connectPairedDevice } from "@/lib/vishnu/account-api";
import { activeConversation, useVishnu, type VishnuData } from "@/lib/vishnu/store";
import type { View } from "@/lib/vishnu/types";
import { cn } from "@/lib/cn";
import { Home } from "./home";
import {
  ActivityPanel,
  DevicesPanel,
  KnowledgePanel,
  MemoryPanel,
  ProjectsPanel,
  SettingsPanel,
  TodayPanel,
} from "./panels";
import { Setup } from "./setup";
import { SignInPanel } from "./signin";
import { WorkspaceSync } from "./sync";
import {
  AgentsPanel,
  AppsPanel,
  CompanionPanel,
  DesktopPanel,
  GraphPanel,
  InboxPanel,
  LivePanel,
  SensoriumPanel,
  SystemPanel,
  TreePanel,
  VaultPanel,
  WorkflowPanel,
} from "./modules";
import {
  ApprovalsPanel,
  DashboardPanel,
  ExtensionsPanel,
  ModelsPanel,
  NotificationsPanel,
  ProductsPanel,
  RelationshipsPanel,
  StoragePanel,
  VoicePanel,
} from "./surfaces";

const PRIMARY: { id: View; label: string; icon: typeof MessageCircle }[] = [
  { id: "home", label: "Home", icon: MessageCircle },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "knowledge", label: "Knowledge", icon: Library },
  { id: "today", label: "Today", icon: Sun },
];

const MORE: { id: View; label: string; icon: typeof MessageCircle }[] = [
  { id: "graph", label: "Graph", icon: Network },
  { id: "tree", label: "Tree", icon: Network },
  { id: "projects", label: "Projects", icon: FolderKanban },
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "live", label: "Live work", icon: Activity },
  { id: "workflows", label: "Workflows", icon: Workflow },
  { id: "apps", label: "Apps", icon: Library },
  { id: "agents", label: "Agents", icon: Brain },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "devices", label: "Devices", icon: Smartphone },
  { id: "companion", label: "Phone", icon: Smartphone },
  { id: "desktop", label: "Desktop", icon: Monitor },
  { id: "vault", label: "Vault", icon: Shield },
  { id: "sensorium", label: "Sensorium", icon: Shield },
  { id: "system", label: "System", icon: Monitor },
  { id: "dashboard", label: "Dashboard", icon: Activity },
  { id: "products", label: "Products", icon: Library },
  { id: "approvals", label: "Approvals", icon: Shield },
  { id: "notifications", label: "Notices", icon: Inbox },
  { id: "relationships", label: "Relationships", icon: Network },
  { id: "voice", label: "Voice", icon: MessageCircle },
  { id: "models", label: "Models", icon: Brain },
  { id: "storage", label: "Storage", icon: Library },
  { id: "extensions", label: "Extensions", icon: Workflow },
  { id: "settings", label: "Settings", icon: Settings },
];

export function VishnuApp() {
  const owner = useVishnu((s) => s.owner);
  const syncState = useVishnu((s) => s.syncState);
  const { user, isPending } = useCurrentUserState();
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    const finish = () => setBooting(false);
    if (useVishnu.persist.hasHydrated()) finish();
    const unsub = useVishnu.persist.onFinishHydration(finish);
    return () => {
      unsub();
    };
  }, []);

  if (booting || isPending) {
    return (
      <main className="app-frame grid place-items-center bg-bg">
        <p className="text-sm font-medium tracking-[0.32em] text-muted">VISHNU</p>
      </main>
    );
  }

  if (!user) return <SignInPanel />;

  let body: React.ReactNode;
  if (syncState === "loading") {
    body = (
      <main className="app-frame grid place-items-center bg-bg px-6 text-center">
        <div>
          <p className="text-sm font-medium tracking-[0.32em] text-muted">VISHNU</p>
          <p className="mt-3 text-sm text-faint">Opening the workspace saved to this account.</p>
        </div>
      </main>
    );
  } else if (!owner) {
    body = <Setup />;
  } else {
    body = <Workspace ownerName={owner.name} />;
  }

  return (
    <>
      <WorkspaceSync />
      {body}
    </>
  );
}

function Workspace({ ownerName }: { ownerName: string }) {
  const view = useVishnu((s) => s.view);
  const setView = useVishnu((s) => s.setView);
  const emergency = useVishnu((s) => s.settings.emergency);
  const autonomy = useVishnu((s) => s.settings.autonomy);
  const conversations = useVishnu((s) => s.conversations);
  const activeId = useVishnu((s) => s.activeId);
  const openChat = useVishnu((s) => s.openChat);
  const syncState = useVishnu((s) => s.syncState);
  const [cloud, setCloud] = useState<"unknown" | "on" | "off">("unknown");
  const [palette, setPalette] = useState(false);
  const [more, setMore] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    aiAvailable()
      .then((res) => {
        if (!cancelled) setCloud(res.available ? "on" : "off");
      })
      .catch(() => {
        if (!cancelled) setCloud("off");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const state = useVishnu.getState();
    if (!state.conversations.length) state.newChat();
    state.touchBrowser();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      }
      if (e.key === "Escape") {
        setPalette(false);
        setMore(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("pair");
    const surface = params.get("surface");
    if (surface === "phone") useVishnu.getState().setView("companion");
    if (surface === "desktop") useVishnu.getState().setView("desktop");
    if (!code) return;
    let stopped = false;
    void connectPairedDevice({ data: { code } })
      .then((res) => {
        if (stopped) return;
        if (res.doc) {
          useVishnu.getState().hydrateFromServer(JSON.parse(res.doc) as Partial<VishnuData>);
          if (surface === "phone") useVishnu.getState().setView("companion");
          if (surface === "desktop") useVishnu.getState().setView("desktop");
        }
        const url = new URL(window.location.href);
        url.searchParams.delete("pair");
        url.searchParams.delete("surface");
        window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
        toast(res.message);
      })
      .catch((error: unknown) => {
        if (!stopped) toast(error instanceof Error ? error.message : "Could not connect");
      });
    return () => {
      stopped = true;
    };
  }, []);

  const current = activeConversation(useVishnu.getState());

  return (
    <div className="app-frame flex bg-bg text-fg">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line md:flex">
        <div className="px-5 pt-6">
          <p className="text-sm font-medium tracking-[0.28em]">VISHNU</p>
          <p className="mt-1 truncate text-xs text-faint">{ownerName}</p>
        </div>
        <div className="scroll-thin mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-4">
          <nav className="flex flex-col gap-1" aria-label="Primary">
            {[...PRIMARY, ...MORE].map((item) => (
              <NavButton key={item.id} item={item} current={view} onSelect={setView} />
            ))}
          </nav>
          <div className="mt-4">
            <p className="px-3 text-xs text-faint">Conversations</p>
            <ul className="mt-1">
              {conversations.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => openChat(c.id)}
                    className={cn(
                      "w-full truncate rounded-xl px-3 py-2 text-left text-sm",
                      c.id === (activeId ?? current?.id) ? "bg-panel text-fg" : "text-muted",
                    )}
                  >
                    {c.title}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="border-t border-line px-5 py-4 text-xs text-faint">
          <p className="capitalize">Autonomy · {autonomy}</p>
          <p className="mt-1">{cloud === "on" ? "Cloud mind ready" : cloud === "off" ? "Cloud mind offline" : "Checking cloud mind"}</p>
          <p className="mt-1">{syncState === "offline" ? "Sync paused on this browser" : "Synced to this account"}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2 md:px-6">
          <p className="text-sm font-medium tracking-[0.22em] md:hidden">VISHNU</p>
          <p className="hidden text-sm text-muted md:block">
            {view === "home" ? current?.title ?? "Home" : labelFor(view)}
          </p>
          <div className="ml-auto flex items-center gap-2">
            {emergency && <span className="text-xs text-danger">Emergency stop</span>}
            <button
              type="button"
              onClick={() => setPalette(true)}
              className="grid size-11 shrink-0 place-items-center rounded-xl border border-line text-muted"
              aria-label="Search workspace"
            >
              <Search className="size-5" />
            </button>
            <div className="min-w-0 max-w-[42vw] overflow-hidden sm:max-w-[220px]">
              <UserButton />
            </div>
          </div>
        </header>
        <main className="min-h-0 flex-1">
          {view === "home" && <Home />}
          {view === "memory" && <MemoryPanel />}
          {view === "graph" && <GraphPanel />}
          {view === "tree" && <TreePanel />}
          {view === "knowledge" && <KnowledgePanel />}
          {view === "today" && <TodayPanel />}
          {view === "projects" && <ProjectsPanel />}
          {view === "inbox" && <InboxPanel />}
          {view === "live" && <LivePanel />}
          {view === "workflows" && <WorkflowPanel />}
          {view === "apps" && <AppsPanel />}
          {view === "agents" && <AgentsPanel />}
          {view === "activity" && <ActivityPanel />}
          {view === "devices" && <DevicesPanel />}
          {view === "companion" && <CompanionPanel />}
          {view === "desktop" && <DesktopPanel />}
          {view === "vault" && <VaultPanel />}
          {view === "sensorium" && <SensoriumPanel />}
          {view === "system" && <SystemPanel />}
          {view === "dashboard" && <DashboardPanel />}
          {view === "products" && <ProductsPanel />}
          {view === "approvals" && <ApprovalsPanel />}
          {view === "notifications" && <NotificationsPanel />}
          {view === "relationships" && <RelationshipsPanel />}
          {view === "voice" && <VoicePanel />}
          {view === "models" && <ModelsPanel />}
          {view === "storage" && <StoragePanel />}
          {view === "extensions" && <ExtensionsPanel />}
          {view === "settings" && <SettingsPanel />}
        </main>
        <nav className="relative grid grid-cols-5 border-t border-line md:hidden" aria-label="Mobile">
          {more && (
            <div className="scroll-thin absolute bottom-full left-0 right-0 z-20 grid max-h-[70dvh] grid-cols-2 gap-2 overflow-y-auto border-t border-line bg-ink p-3">
              {MORE.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setView(item.id);
                    setMore(false);
                  }}
                  className="flex h-12 items-center gap-2 rounded-xl border border-line px-3 text-sm"
                >
                  <item.icon className="size-4" />
                  {item.label}
                </button>
              ))}
            </div>
          )}
          {PRIMARY.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                setMore(false);
                setView(item.id);
              }}
              className={cn(
                "flex h-16 flex-col items-center justify-center gap-1 text-xs",
                view === item.id ? "text-accent" : "text-faint",
              )}
            >
              <item.icon className="size-5" />
              {item.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setMore((v) => !v)}
            className={cn(
              "flex h-16 flex-col items-center justify-center gap-1 text-xs",
              more || MORE.some((m) => m.id === view) ? "text-accent" : "text-faint",
            )}
          >
            <Ellipsis className="size-5" />
            More
          </button>
        </nav>
      </div>

      {palette && (
        <div className="fixed inset-0 z-40 grid place-items-start bg-bg/80 px-4 pt-24" role="dialog" aria-label="Search">
          <div className="mx-auto w-full max-w-lg rounded-2xl border border-line bg-ink p-3 shadow-2xl">
            <div className="flex items-center gap-2">
              <Search className="size-4 text-faint" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search memory, knowledge, tasks, chats"
                className="h-11 flex-1 bg-transparent text-base outline-none"
                aria-label="Search"
              />
              <button type="button" onClick={() => setPalette(false)} aria-label="Close search" className="grid size-11 place-items-center">
                <X className="size-5" />
              </button>
            </div>
            <SearchResults
              query={query}
              onPick={(next) => {
                setPalette(false);
                setQuery("");
                setView(next);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function NavButton({
  item,
  current,
  onSelect,
}: {
  item: { id: View; label: string; icon: typeof MessageCircle };
  current: View;
  onSelect: (view: View) => void;
}) {
  const Icon = item.icon;
  const on = current === item.id;
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      aria-current={on ? "page" : undefined}
      className={cn(
        "flex h-11 items-center gap-3 rounded-xl px-3 text-sm",
        on ? "bg-panel text-fg" : "text-muted hover:text-fg",
      )}
    >
      <Icon className="size-4" />
      {item.label}
    </button>
  );
}

function labelFor(view: View) {
  return [...PRIMARY, ...MORE].find((i) => i.id === view)?.label ?? "Vishnu";
}

function SearchResults({ query, onPick }: { query: string; onPick: (view: View) => void }) {
  const memories = useVishnu((s) => s.memories);
  const knowledge = useVishnu((s) => s.knowledge);
  const tasks = useVishnu((s) => s.tasks);
  const inbox = useVishnu((s) => s.inbox);
  const conversations = useVishnu((s) => s.conversations);
  const openChat = useVishnu((s) => s.openChat);
  const q = query.trim().toLowerCase();
  if (!q) return <p className="px-2 py-4 text-sm text-faint">Type to search this device.</p>;
  const rows = [
    ...memories
      .filter((m) => `${m.title} ${m.body}`.toLowerCase().includes(q))
      .slice(0, 5)
      .map((m) => ({ id: m.id, label: m.title, view: "memory" as View })),
    ...knowledge
      .filter((k) => `${k.title} ${k.body}`.toLowerCase().includes(q))
      .slice(0, 5)
      .map((k) => ({ id: k.id, label: k.title, view: "knowledge" as View })),
    ...tasks
      .filter((t) => t.title.toLowerCase().includes(q))
      .slice(0, 5)
      .map((t) => ({ id: t.id, label: t.title, view: "today" as View })),
    ...conversations
      .filter((c) => c.title.toLowerCase().includes(q) || c.messages.some((m) => m.content.toLowerCase().includes(q)))
      .slice(0, 5)
      .map((c) => ({ id: c.id, label: c.title, view: "home" as View, chat: true })),
    ...inbox
      .filter((item) => `${item.title} ${item.body}`.toLowerCase().includes(q))
      .slice(0, 4)
      .map((item) => ({ id: item.id, label: item.title, view: "inbox" as View })),
  ];
  if (!rows.length) return <p className="px-2 py-4 text-sm text-faint">No matches.</p>;
  return (
    <ul className="mt-2 max-h-72 overflow-y-auto">
      {rows.map((row) => (
        <li key={`${row.view}-${row.id}`}>
          <button
            type="button"
            className="flex h-11 w-full items-center rounded-xl px-2 text-left text-sm hover:bg-panel"
            onClick={() => {
              if ("chat" in row && row.chat) openChat(row.id);
              onPick(row.view);
            }}
          >
            <span className="w-24 shrink-0 text-xs capitalize text-faint">{row.view}</span>
            <span className="truncate">{row.label}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
