import { useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { useVishnu, workspaceSnapshot, type VishnuData } from "@/lib/vishnu/store";
import { readDocument } from "@/lib/vishnu/files";
import type { Autonomy, DeviceItem, MemoryKind, ProjectItem } from "@/lib/vishnu/types";
import { AccountAccess, PairingCode } from "./account";
import { cn } from "@/lib/cn";

function Page({
  title,
  lede,
  children,
}: {
  title: string;
  lede: string;
  children: ReactNode;
}) {
  return (
    <div className="scroll-thin h-full overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-medium tracking-tight">{title}</h1>
        <p className="mt-1 text-sm leading-relaxed text-muted">{lede}</p>
        <div className="mt-6">{children}</div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm text-muted">
      {label}
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 h-11 w-full rounded-xl border border-line bg-ink px-3 text-base text-fg outline-none"
      />
    </label>
  );
}

export function MemoryPanel() {
  const memories = useVishnu((s) => s.memories);
  const addMemory = useVishnu((s) => s.addMemory);
  const updateMemory = useVishnu((s) => s.updateMemory);
  const deleteMemory = useVishnu((s) => s.deleteMemory);
  const [q, setQ] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [kind, setKind] = useState<MemoryKind>("fact");
  const [editing, setEditing] = useState<string | null>(null);
  const shown = memories.filter((m) =>
    `${m.title} ${m.body}`.toLowerCase().includes(q.trim().toLowerCase()),
  );

  return (
    <Page title="Memory" lede="Facts you want kept apart from documents. Sensitive items stay out of the cloud mind unless you allow it.">
      <form
        className="grid gap-3 rounded-2xl border border-line bg-ink p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim() || !body.trim()) return;
          addMemory({ title, body, kind });
          setTitle("");
          setBody("");
          toast("Memory saved on this device.");
        }}
      >
        <Field label="Title" value={title} onChange={setTitle} placeholder="A short name" />
        <label className="block text-sm text-muted">
          What to remember
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="mt-1 min-h-20 w-full rounded-xl border border-line bg-bg px-3 py-2 text-base text-fg outline-none"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as MemoryKind)}
            className="h-11 rounded-xl border border-line bg-bg px-3 text-sm"
            aria-label="Memory kind"
          >
            <option value="fact">Fact</option>
            <option value="preference">Preference</option>
            <option value="person">Person</option>
            <option value="note">Note</option>
          </select>
          <button type="submit" className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink">
            Remember
          </button>
        </div>
      </form>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search memory"
        className="mt-4 h-11 w-full rounded-xl border border-line bg-ink px-3 text-base outline-none"
        aria-label="Search memory"
      />
      <ul className="mt-4 grid gap-3">
        {shown.length === 0 && (
          <li className="rounded-2xl border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
            Nothing stored yet.
          </li>
        )}
        {shown.map((m) => (
          <li key={m.id} className="rounded-2xl border border-line bg-ink p-4">
            {editing === m.id ? (
              <form
                className="grid gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  setEditing(null);
                }}
              >
                <input
                  value={m.title}
                  onChange={(e) => updateMemory(m.id, { title: e.target.value })}
                  className="h-11 rounded-xl border border-line bg-bg px-3 text-base"
                  aria-label="Edit title"
                />
                <textarea
                  value={m.body}
                  onChange={(e) => updateMemory(m.id, { body: e.target.value })}
                  className="min-h-20 rounded-xl border border-line bg-bg px-3 py-2 text-base"
                  aria-label="Edit memory"
                />
                <button type="submit" className="h-10 w-fit rounded-xl bg-accent px-3 text-sm font-medium text-accent-ink">
                  Done
                </button>
              </form>
            ) : (
              <>
                <div className="flex items-start justify-between gap-3">
                  <h2 className="font-medium">{m.title}</h2>
                  <span className="text-xs capitalize text-faint">{m.kind}</span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-muted whitespace-pre-wrap">{m.body}</p>
              </>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={() => setEditing(editing === m.id ? null : m.id)} className="h-10 rounded-xl border border-line px-3 text-sm">
                Edit
              </button>
              <button
                type="button"
                onClick={() => updateMemory(m.id, { sensitive: !m.sensitive })}
                className={cn("h-10 rounded-xl border px-3 text-sm", m.sensitive ? "border-accent text-accent" : "border-line")}
              >
                {m.sensitive ? "Sensitive" : "Mark sensitive"}
              </button>
              <button
                type="button"
                onClick={() => deleteMemory(m.id)}
                className="h-10 rounded-xl border border-line px-3 text-sm text-danger"
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function KnowledgePanel() {
  const knowledge = useVishnu((s) => s.knowledge);
  const addKnowledge = useVishnu((s) => s.addKnowledge);
  const deleteKnowledge = useVishnu((s) => s.deleteKnowledge);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [q, setQ] = useState("");
  const shown = knowledge.filter((k) => `${k.title} ${k.body}`.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <Page title="Knowledge" lede="Notes and files you can search. PDF, Word, Excel, CSV, and plain text are read in this browser, up to 8 MB and about 20,000 characters.">
      <form
        className="grid gap-3 rounded-2xl border border-line bg-ink p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!body.trim()) return;
          addKnowledge({ title: title || "Untitled note", body });
          setTitle("");
          setBody("");
        }}
      >
        <Field label="Title" value={title} onChange={setTitle} placeholder="Source name" />
        <label className="block text-sm text-muted">
          Text
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="mt-1 min-h-28 w-full rounded-xl border border-line bg-bg px-3 py-2 text-base text-fg outline-none"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button type="submit" className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink">
            File note
          </button>
          <label className="grid h-11 cursor-pointer place-items-center rounded-xl border border-line px-4 text-sm">
            Upload a file
            <input
              type="file"
              accept=".txt,.md,.csv,.json,.pdf,.docx,.xlsx,.xls,text/plain,application/pdf"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                void readDocument(file)
                  .then((doc) => {
                    if (!doc.body.trim()) {
                      toast("That file had no readable text.");
                      return;
                    }
                    addKnowledge(doc);
                    toast(`Filed ${file.name}`);
                  })
                  .catch((error: unknown) => {
                    toast(error instanceof Error ? error.message : "Could not read that file.");
                  });
              }}
            />
          </label>
        </div>
      </form>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search knowledge"
        aria-label="Search knowledge"
        className="mt-4 h-11 w-full rounded-xl border border-line bg-ink px-3 text-base outline-none"
      />
      <ul className="mt-4 grid gap-3">
        {shown.length === 0 && (
          <li className="rounded-2xl border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
            No sources yet.
          </li>
        )}
        {shown.map((k) => (
          <li key={k.id} className="rounded-2xl border border-line bg-ink p-4">
            <h2 className="font-medium">{k.title}</h2>
            <p className="mt-2 line-clamp-4 text-sm leading-relaxed text-muted whitespace-pre-wrap">{k.body}</p>
            <button
              type="button"
              onClick={() => deleteKnowledge(k.id)}
              className="mt-3 h-10 rounded-xl border border-line px-3 text-sm text-danger"
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function TodayPanel() {
  const tasks = useVishnu((s) => s.tasks);
  const routines = useVishnu((s) => s.routines);
  const addTask = useVishnu((s) => s.addTask);
  const toggleTask = useVishnu((s) => s.toggleTask);
  const deleteTask = useVishnu((s) => s.deleteTask);
  const setDraft = useVishnu((s) => s.setDraft);
  const setView = useVishnu((s) => s.setView);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const open = tasks.filter((t) => !t.done);
  const done = tasks.filter((t) => t.done);

  return (
    <Page title="Today" lede="Tasks you or Vishnu add, plus routines that fill the composer. Running a routine does not spend a request until you send it.">
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          addTask(title, due);
          setTitle("");
          setDue("");
        }}
      >
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Add a task"
          aria-label="Task"
          className="h-11 flex-1 rounded-xl border border-line bg-ink px-3 text-base outline-none"
        />
        <input
          value={due}
          onChange={(e) => setDue(e.target.value)}
          placeholder="When"
          aria-label="When"
          className="h-11 rounded-xl border border-line bg-ink px-3 text-base outline-none sm:w-36"
        />
        <button type="submit" className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink">
          Add
        </button>
      </form>
      <section className="mt-6">
        <h2 className="text-sm font-medium text-muted">Open · {open.length}</h2>
        <ul className="mt-2 grid gap-2">
          {open.length === 0 && <li className="text-sm text-faint">Nothing open.</li>}
          {open.map((t) => (
            <li key={t.id} className="flex items-center gap-3 rounded-2xl border border-line bg-ink px-3 py-2">
              <input type="checkbox" checked={false} onChange={() => toggleTask(t.id)} aria-label={`Complete ${t.title}`} className="size-4" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{t.title}</p>
                {t.due && <p className="text-xs text-faint">{t.due}</p>}
              </div>
              <button type="button" onClick={() => deleteTask(t.id)} className="h-10 px-2 text-sm text-danger">
                Delete
              </button>
            </li>
          ))}
        </ul>
      </section>
      {done.length > 0 && (
        <section className="mt-6">
          <h2 className="text-sm font-medium text-muted">Done</h2>
          <ul className="mt-2 grid gap-2">
            {done.map((t) => (
              <li key={t.id} className="flex items-center gap-3 rounded-2xl border border-line px-3 py-2 text-faint">
                <input type="checkbox" checked onChange={() => toggleTask(t.id)} aria-label={`Reopen ${t.title}`} className="size-4" />
                <span className="text-sm line-through">{t.title}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="mt-8">
        <h2 className="text-sm font-medium text-muted">Routines</h2>
        <ul className="mt-2 grid gap-2">
          {routines.map((r) => (
            <li key={r.id} className="rounded-2xl border border-line bg-ink p-4">
              <h3 className="font-medium">{r.title}</h3>
              <p className="mt-1 text-sm text-muted">{r.prompt}</p>
              <button
                type="button"
                className="mt-3 h-10 rounded-xl border border-line px-3 text-sm"
                onClick={() => {
                  setDraft(r.prompt);
                  setView("home");
                }}
              >
                Use in conversation
              </button>
            </li>
          ))}
        </ul>
      </section>
    </Page>
  );
}

export function ProjectsPanel() {
  const projects = useVishnu((s) => s.projects);
  const addProject = useVishnu((s) => s.addProject);
  const updateProject = useVishnu((s) => s.updateProject);
  const deleteProject = useVishnu((s) => s.deleteProject);
  const [title, setTitle] = useState("");
  const [intent, setIntent] = useState("");
  const [next, setNext] = useState("");

  return (
    <Page title="Projects" lede="Work with an outcome, not a single reminder.">
      <form
        className="grid gap-3 rounded-2xl border border-line bg-ink p-4"
        onSubmit={(e) => {
          e.preventDefault();
          addProject({ title, intent, next });
          setTitle("");
          setIntent("");
          setNext("");
        }}
      >
        <Field label="Name" value={title} onChange={setTitle} />
        <Field label="Intent" value={intent} onChange={setIntent} placeholder="What done looks like" />
        <Field label="Next step" value={next} onChange={setNext} />
        <button type="submit" className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink">
          Open project
        </button>
      </form>
      <ul className="mt-4 grid gap-3">
        {projects.length === 0 && (
          <li className="rounded-2xl border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
            No projects yet.
          </li>
        )}
        {projects.map((p) => (
          <li key={p.id} className="rounded-2xl border border-line bg-ink p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-medium">{p.title}</h2>
              <select
                value={p.status}
                aria-label={`Status for ${p.title}`}
                onChange={(e) => updateProject(p.id, { status: e.target.value as ProjectItem["status"] })}
                className="h-10 rounded-xl border border-line bg-bg px-2 text-sm"
              >
                <option value="idea">Idea</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="done">Done</option>
              </select>
            </div>
            {p.intent && <p className="mt-2 text-sm text-muted">{p.intent}</p>}
            <label className="mt-3 block text-xs text-faint">
              Next
              <input
                value={p.next}
                onChange={(e) => updateProject(p.id, { next: e.target.value })}
                className="mt-1 h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm text-fg"
              />
            </label>
            <button type="button" onClick={() => deleteProject(p.id)} className="mt-3 h-10 text-sm text-danger">
              Delete project
            </button>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function ActivityPanel() {
  const activity = useVishnu((s) => s.activity);
  const [q, setQ] = useState("");
  const shown = activity.filter((a) => `${a.kind} ${a.detail}`.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <Page title="Activity" lede="A local record of setup, memory, knowledge, tasks, devices, and security changes.">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Filter activity"
        aria-label="Filter activity"
        className="h-11 w-full rounded-xl border border-line bg-ink px-3 text-base outline-none"
      />
      <ul className="mt-4 divide-y divide-line rounded-2xl border border-line bg-ink">
        {shown.length === 0 && <li className="px-4 py-8 text-center text-sm text-muted">No events.</li>}
        {shown.map((a) => (
          <li key={a.id} className="px-4 py-3">
            <p className="text-sm">{a.detail}</p>
            <p className="mt-1 text-xs text-faint">
              {a.kind} · {new Date(a.at).toLocaleString()}
            </p>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function DevicesPanel() {
  const devices = useVishnu((s) => s.devices);
  const addDevice = useVishnu((s) => s.addDevice);
  const revokeDevice = useVishnu((s) => s.revokeDevice);
  const setView = useVishnu((s) => s.setView);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<DeviceItem["kind"]>("phone");

  return (
    <Page title="Devices" lede="Create a phone, then scan its code with that handset’s camera. The link opens Vishnu on the same account and marks the device connected. You can also type the code on Phone. This is the installed browser, not a separate radio app.">
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          const device = addDevice({ name, kind });
          setName("");
          toast(`Code ready: ${device.code}`);
        }}
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Device name"
          aria-label="Device name"
          className="h-11 flex-1 rounded-xl border border-line bg-ink px-3 text-base outline-none"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as DeviceItem["kind"])}
          aria-label="Device kind"
          className="h-11 rounded-xl border border-line bg-ink px-3 text-sm"
        >
          <option value="phone">Phone</option>
          <option value="desktop">Desktop</option>
          <option value="browser">Browser</option>
          <option value="other">Other</option>
        </select>
        <button type="submit" className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink">
          Create code
        </button>
      </form>
      <button type="button" onClick={() => setView("companion")} className="mt-3 h-10 text-sm text-accent">
        Open the phone companion
      </button>
      <ul className="mt-4 grid gap-3">
        {devices.map((d) => {
          const state = d.revoked ? "Revoked" : d.connected ? "Connected" : "Waiting";
          return (
            <li key={d.id} className="rounded-2xl border border-line bg-ink p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-medium">{d.name}</h2>
                  <p className="mt-1 text-xs capitalize text-faint">
                    {d.kind} · {state}
                  </p>
                </div>
                <p className="font-mono text-xs text-accent">{d.code}</p>
              </div>
              <p className="mt-2 text-xs text-muted">
                Last seen {new Date(d.lastSeen).toLocaleString()} · {d.scopes.join(", ")}
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  className="h-10 rounded-xl border border-line px-3 text-sm"
                  onClick={() => {
                    void navigator.clipboard.writeText(d.code).then(
                      () => toast("Code copied."),
                      () => toast(d.code),
                    );
                  }}
                >
                  Copy code
                </button>
                {!d.revoked && d.name !== "This browser" && (
                  <button type="button" onClick={() => revokeDevice(d.id)} className="h-10 text-sm text-danger">
                    Revoke
                  </button>
                )}
              </div>
              {!d.revoked && <PairingCode code={d.code} />}
            </li>
          );
        })}
      </ul>
    </Page>
  );
}

const MODES: Autonomy[] = ["observe", "suggest", "ask", "act"];

export function SettingsPanel() {
  const owner = useVishnu((s) => s.owner);
  const settings = useVishnu((s) => s.settings);
  const setAutonomy = useVishnu((s) => s.setAutonomy);
  const setVoice = useVishnu((s) => s.setVoice);
  const setEmergency = useVishnu((s) => s.setEmergency);
  const setIncludeSensitive = useVishnu((s) => s.setIncludeSensitive);
  const resetWorkspace = useVishnu((s) => s.resetWorkspace);
  const importData = useVishnu((s) => s.importData);
  const [showCodes, setShowCodes] = useState(false);
  const [resetText, setResetText] = useState("");
  const snapshot = useVishnu();

  const file = useMemo(() => workspaceSnapshot(snapshot), [snapshot]);

  return (
    <Page title="Settings" lede="Control how Vishnu behaves. Cloud reasoning never runs by itself. The workspace syncs to the signed-in account. The vault passphrase does not.">
      <section className="rounded-2xl border border-line bg-ink p-4">
        <h2 className="font-medium">Autonomy</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setAutonomy(mode)}
              className={cn(
                "h-10 rounded-full border px-4 text-sm capitalize",
                settings.autonomy === mode ? "border-accent bg-accent text-accent-ink" : "border-line",
              )}
            >
              {mode}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-3 divide-y divide-line rounded-2xl border border-line bg-ink">
        <Toggle
          label="Speak replies"
          detail="Uses this browser’s voice. Off by default."
          on={settings.voice}
          onClick={() => setVoice(!settings.voice)}
        />
        <Toggle
          label="Include sensitive memories"
          detail="When off, items you mark sensitive are not sent with a message."
          on={settings.includeSensitive}
          onClick={() => setIncludeSensitive(!settings.includeSensitive)}
        />
        <Toggle
          label="Emergency stop"
          detail="Blocks new writes from conversation, including Act mode."
          on={settings.emergency}
          onClick={() => setEmergency(!settings.emergency)}
        />
      </section>

      <section className="mt-3 rounded-2xl border border-line bg-ink p-4">
        <h2 className="font-medium">Data</h2>
        <p className="mt-1 text-sm text-muted">
          Saved in this browser and copied to the signed-in account. The vault stays ciphertext. Export is a backup, not a second passphrase.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="h-11 rounded-xl border border-line px-4 text-sm"
            onClick={() => {
              const blob = new Blob([JSON.stringify({ version: 2, ...file, exportedAt: new Date().toISOString() }, null, 2)], {
                type: "application/json",
              });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "vishnu-workspace.json";
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Export workspace
          </button>
          <label className="grid h-11 cursor-pointer place-items-center rounded-xl border border-line px-4 text-sm">
            Import workspace
            <input
              type="file"
              accept="application/json"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                const reader = new FileReader();
                reader.onload = () => {
                  try {
                    const data = JSON.parse(String(reader.result)) as { version?: number; owner?: { name?: string } };
                    if ((data.version !== 1 && data.version !== 2) || !data.owner?.name) {
                      toast("That file is not a Vishnu workspace.");
                      return;
                    }
                    importData(data as Partial<VishnuData>);
                    toast("Workspace restored.");
                  } catch {
                    toast("Could not read that file.");
                  }
                };
                reader.readAsText(f);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      </section>

      <section className="mt-3 rounded-2xl border border-line bg-ink p-4">
        <h2 className="font-medium">Recovery codes</h2>
        <p className="mt-1 text-sm text-muted">Saved with this browser workspace. They are not a vault key.</p>
        <button type="button" onClick={() => setShowCodes((v) => !v)} className="mt-3 h-10 text-sm text-accent">
          {showCodes ? "Hide codes" : "Show codes"}
        </button>
        {showCodes && (
          <ul className="mt-3 grid gap-1 sm:grid-cols-2">
            {owner?.recoveryCodes.map((code) => (
              <li key={code} className="font-mono text-sm text-accent">
                {code}
              </li>
            ))}
          </ul>
        )}
      </section>

      <AccountAccess />

      <section className="mt-3 rounded-2xl border border-line bg-ink p-4">
        <h2 className="font-medium">About this workspace</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Talk, memory, knowledge, tasks, and projects follow the account you signed in with. Create a passkey or recovery codes above before you open Vishnu on another computer. Install the phone or desktop screen from System, then scan a device code with the handset.
        </p>
      </section>

      <section className="mt-3 rounded-2xl border border-danger/40 bg-ink p-4">
        <h2 className="font-medium text-danger">Reset workspace</h2>
        <p className="mt-1 text-sm text-muted">Deletes everything saved in this browser. Export first if you want a copy.</p>
        <input
          value={resetText}
          onChange={(e) => setResetText(e.target.value)}
          placeholder="Type RESET"
          aria-label="Type RESET to confirm"
          className="mt-3 h-11 w-full rounded-xl border border-line bg-bg px-3 text-base outline-none"
        />
        <button
          type="button"
          disabled={resetText !== "RESET"}
          onClick={() => resetWorkspace()}
          className="mt-3 h-11 rounded-xl border border-danger px-4 text-sm text-danger disabled:opacity-40"
        >
          Reset
        </button>
      </section>
    </Page>
  );
}

function Toggle({
  label,
  detail,
  on,
  onClick,
}: {
  label: string;
  detail: string;
  on: boolean;
  onClick: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">{detail}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        onClick={onClick}
        className={cn("relative h-7 w-12 shrink-0 rounded-full", on ? "bg-accent" : "bg-line")}
      >
        <span
          className={cn(
            "absolute top-0.5 size-6 rounded-full bg-fg transition-transform",
            on ? "translate-x-5 bg-accent-ink" : "translate-x-0.5",
          )}
        />
        <span className="sr-only">{label}</span>
      </button>
    </div>
  );
}
