import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { useVishnu } from "@/lib/vishnu/store";
import { openVault, sealVault, type Secret } from "@/lib/vishnu/vault";
import { InstallActions, useOutsideRead } from "./account";
import type { MemoryItem } from "@/lib/vishnu/types";

function Page({ title, lede, children }: { title: string; lede: string; children: ReactNode }) {
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
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block text-sm text-muted">
      {label}
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        autoComplete={type === "password" ? "new-password" : undefined}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 h-11 w-full rounded-xl border border-line bg-ink px-3 text-base text-fg outline-none"
      />
    </label>
  );
}

const KIND_COLOR: Record<MemoryItem["kind"], string> = {
  fact: "#5ad4ff",
  preference: "#c4b5fd",
  person: "#86efac",
  note: "#fcd34d",
};

export function GraphPanel() {
  const memories = useVishnu((s) => s.memories);
  const links = useVishnu((s) => s.links);
  const linkMemories = useVishnu((s) => s.linkMemories);
  const unlink = useVishnu((s) => s.unlink);
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [label, setLabel] = useState("related");
  const [selected, setSelected] = useState<string | null>(null);
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const nodes = useMemo(() => {
    const placed = layout(memories);
    return placed.map((node) => ({ ...node, ...positions[node.id] }));
  }, [memories, positions]);
  const focus = memories.find((m) => m.id === selected) ?? null;
  const focusLinks = links.filter((link) => link.fromId === selected || link.toId === selected);

  return (
    <Page
      title="Memory graph"
      lede="Drag a memory. Link two that belong together. A line only exists when you add it, or when you accept a suggestion from words already in both memories."
    >
      <form
        className="grid gap-2 sm:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!fromId || !toId || fromId === toId) {
            toast("Choose two different memories.");
            return;
          }
          linkMemories(fromId, toId, label);
        }}
      >
        <select value={fromId} onChange={(e) => setFromId(e.target.value)} aria-label="From memory" className="h-11 rounded-xl border border-line bg-ink px-2 text-sm">
          <option value="">From</option>
          {memories.map((m) => (
            <option key={m.id} value={m.id}>{m.title}</option>
          ))}
        </select>
        <select value={toId} onChange={(e) => setToId(e.target.value)} aria-label="To memory" className="h-11 rounded-xl border border-line bg-ink px-2 text-sm">
          <option value="">To</option>
          {memories.map((m) => (
            <option key={m.id} value={m.id}>{m.title}</option>
          ))}
        </select>
        <input value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Link label" className="h-11 rounded-xl border border-line bg-ink px-3 text-sm" />
        <button type="submit" className="h-11 rounded-xl bg-accent text-sm font-medium text-accent-ink">Link</button>
      </form>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-faint">
        {(Object.keys(KIND_COLOR) as MemoryItem["kind"][]).map((kind) => (
          <span key={kind} className="inline-flex items-center gap-1 capitalize">
            <span className="inline-block size-2 rounded-full" style={{ background: KIND_COLOR[kind] }} />
            {kind}
          </span>
        ))}
        <button
          type="button"
          className="h-9 rounded-full border border-line px-3 text-fg"
          onClick={() => {
            const ideas = suggestLinks(memories, links);
            if (!ideas.length) {
              toast("No shared words to link yet.");
              return;
            }
            for (const idea of ideas) linkMemories(idea.fromId, idea.toId, idea.label);
            toast(`Added ${ideas.length} link${ideas.length === 1 ? "" : "s"} from shared words.`);
          }}
        >
          Suggest from shared words
        </button>
      </div>
      <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-ink">
        <svg viewBox="0 0 640 380" className="h-80 w-full min-w-[640px] touch-none" role="img" aria-label="Memory graph">
          {links.map((link) => {
            const a = nodes.find((n) => n.id === link.fromId);
            const b = nodes.find((n) => n.id === link.toId);
            if (!a || !b) return null;
            const active = selected === link.fromId || selected === link.toId;
            return (
              <g key={link.id}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={active ? "#5ad4ff" : "#2a3a52"} strokeWidth={active ? 2 : 1.5} />
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6} textAnchor="middle" fill="#8b97ab" fontSize="10">
                  {link.label}
                </text>
              </g>
            );
          })}
          {nodes.map((node) => (
            <g
              key={node.id}
              className="cursor-pointer"
              onPointerDown={(event) => {
                const svg = event.currentTarget.ownerSVGElement;
                if (!svg) return;
                const start = svgPoint(svg, event.clientX, event.clientY);
                const origin = { x: node.x, y: node.y };
                const move = (ev: PointerEvent) => {
                  const next = svgPoint(svg, ev.clientX, ev.clientY);
                  setPositions((prev) => ({
                    ...prev,
                    [node.id]: {
                      x: clamp(origin.x + next.x - start.x, 36, 604),
                      y: clamp(origin.y + next.y - start.y, 28, 340),
                    },
                  }));
                };
                const up = () => {
                  window.removeEventListener("pointermove", move);
                  window.removeEventListener("pointerup", up);
                };
                window.addEventListener("pointermove", move);
                window.addEventListener("pointerup", up);
              }}
              onClick={() => setSelected(node.id)}
            >
              <circle cx={node.x} cy={node.y} r={selected === node.id ? 18 : 14} fill="#101826" stroke={KIND_COLOR[node.kind]} strokeWidth={selected === node.id ? 3 : 2} />
              <text x={node.x} y={node.y + 30} textAnchor="middle" fill="#eef3fb" fontSize="11">
                {node.title.slice(0, 22)}
              </text>
            </g>
          ))}
        </svg>
      </div>
      {memories.length === 0 && <p className="mt-3 text-sm text-muted">Save a memory first. The graph only draws what you have stored.</p>}
      {focus && (
        <section className="mt-4 rounded-2xl border border-line bg-ink p-4">
          <p className="text-xs capitalize text-faint">{focus.kind}</p>
          <h2 className="font-medium">{focus.title}</h2>
          <p className="mt-1 text-sm text-muted">{focus.body}</p>
          <ul className="mt-3 grid gap-1 text-sm">
            {focusLinks.length === 0 && <li className="text-muted">No links from this memory yet.</li>}
            {focusLinks.map((link) => (
              <li key={link.id}>
                {nameOf(memories, link.fromId)} → {nameOf(memories, link.toId)} · {link.label}
              </li>
            ))}
          </ul>
        </section>
      )}
      <ul className="mt-4 grid gap-2">
        {links.map((link) => (
          <li key={link.id} className="flex items-center justify-between gap-3 rounded-xl border border-line px-3 py-2 text-sm">
            <span className="min-w-0 truncate">{nameOf(memories, link.fromId)} → {nameOf(memories, link.toId)} · {link.label}</span>
            <button type="button" onClick={() => unlink(link.id)} className="h-10 shrink-0 text-danger">Remove</button>
          </li>
        ))}
      </ul>
    </Page>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function svgPoint(svg: SVGSVGElement, clientX: number, clientY: number) {
  const matrix = svg.getScreenCTM();
  if (!matrix) return { x: 0, y: 0 };
  const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
  return { x: point.x, y: point.y };
}

function suggestLinks(memories: MemoryItem[], links: { fromId: string; toId: string }[]) {
  const stop = new Set(["that", "this", "with", "from", "your", "have", "about", "into", "what", "when", "they", "them", "and"]);
  const words = (memory: MemoryItem) =>
    new Set(
      `${memory.title} ${memory.body}`
        .toLowerCase()
        .split(/[^a-z0-9]+/)
        .filter((word) => word.length > 2 && !stop.has(word)),
    );
  const exists = (a: string, b: string) => links.some((link) => (link.fromId === a && link.toId === b) || (link.fromId === b && link.toId === a));
  const ideas: { fromId: string; toId: string; label: string }[] = [];
  for (let i = 0; i < memories.length; i += 1) {
    for (let j = i + 1; j < memories.length; j += 1) {
      const left = memories[i];
      const right = memories[j];
      if (!left || !right || exists(left.id, right.id)) continue;
      const shared = [...words(left)].find((word) => words(right).has(word));
      if (shared) ideas.push({ fromId: left.id, toId: right.id, label: shared });
      if (ideas.length === 8) return ideas;
    }
  }
  return ideas;
}

function nameOf(memories: MemoryItem[], id: string) {
  return memories.find((m) => m.id === id)?.title ?? "Missing";
}

function layout(memories: MemoryItem[]) {
  const count = Math.max(memories.length, 1);
  return memories.map((memory, index) => {
    const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
    const ring = memories.length > 10 ? 1 + Math.floor(index / 10) * 0.15 : 1;
    return {
      id: memory.id,
      title: memory.title,
      kind: memory.kind,
      x: 320 + Math.cos(angle) * 150 * ring,
      y: 180 + Math.sin(angle) * 120 * ring,
    };
  });
}

export function TreePanel() {
  const memories = useVishnu((s) => s.memories);
  const links = useVishnu((s) => s.links);
  const targeted = new Set(links.map((link) => link.toId));
  const roots = memories.filter((memory) => !targeted.has(memory.id));
  const shown = roots.length ? roots : memories;
  return (
    <Page title="Memory tree" lede="Roots are memories nothing points at. Children follow the links you made on the graph. Kinds stay visible so an unlinked memory is not lost.">
      {memories.length === 0 && <p className="text-sm text-muted">No memories yet.</p>}
      <ul className="grid gap-3">
        {shown.map((memory) => (
          <MemoryBranch key={memory.id} id={memory.id} memories={memories} links={links} depth={0} seen={new Set()} />
        ))}
      </ul>
    </Page>
  );
}

function MemoryBranch({
  id,
  memories,
  links,
  depth,
  seen,
}: {
  id: string;
  memories: MemoryItem[];
  links: { id: string; fromId: string; toId: string; label: string }[];
  depth: number;
  seen: Set<string>;
}) {
  if (seen.has(id) || depth > 8) return null;
  const memory = memories.find((item) => item.id === id);
  if (!memory) return null;
  const next = new Set(seen);
  next.add(id);
  const children = links.filter((link) => link.fromId === id);
  return (
    <li className="rounded-2xl border border-line bg-ink p-4" style={{ marginLeft: depth ? 12 : 0 }}>
      <p className="text-xs capitalize text-faint">{memory.kind}</p>
      <p className="font-medium">{memory.title}</p>
      <p className="text-sm text-muted">{memory.body}</p>
      {children.length > 0 && (
        <ul className="mt-3 grid gap-2 border-l border-line pl-3">
          {children.map((link) => (
            <li key={link.id}>
              <p className="text-xs text-accent">{link.label}</p>
              <MemoryBranch id={link.toId} memories={memories} links={links} depth={depth + 1} seen={next} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function InboxPanel() {
  const inbox = useVishnu((s) => s.inbox);
  const toggleInbox = useVishnu((s) => s.toggleInbox);
  const addInbox = useVishnu((s) => s.addInbox);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  return (
    <Page title="Inbox" lede="Things that need a look. Workflows and automations land here. Marking one read does not delete it.">
      <form
        className="grid gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          addInbox(title, body);
          setTitle("");
          setBody("");
        }}
      >
        <Field label="Title" value={title} onChange={setTitle} />
        <Field label="Detail" value={body} onChange={setBody} />
        <button type="submit" className="h-11 rounded-xl bg-accent text-sm font-medium text-accent-ink">Add to inbox</button>
      </form>
      <ul className="mt-4 grid gap-2">
        {inbox.length === 0 && <li className="text-sm text-muted">Inbox is clear.</li>}
        {inbox.map((item) => (
          <li key={item.id} className="rounded-2xl border border-line bg-ink p-4">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-medium">{item.title}</h2>
              <button type="button" onClick={() => toggleInbox(item.id)} className="h-10 text-sm text-accent">
                {item.read ? "Unread" : "Mark read"}
              </button>
            </div>
            <p className="mt-1 text-sm whitespace-pre-wrap text-muted">{item.body}</p>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function LivePanel() {
  const jobs = useVishnu((s) => s.jobs);
  return (
    <Page title="Live work" lede="Jobs created when you run a workflow or brief an agent. They record what already happened. They do not keep running after you leave.">
      <ul className="grid gap-2">
        {jobs.length === 0 && <li className="text-sm text-muted">No live work.</li>}
        {jobs.map((job) => (
          <li key={job.id} className="rounded-2xl border border-line bg-ink p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-medium">{job.title}</h2>
              <span className="text-xs capitalize text-faint">{job.status} · {job.progress}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg">
              <div className="h-full bg-accent" style={{ width: `${job.progress}%` }} />
            </div>
            <p className="mt-2 text-sm whitespace-pre-wrap text-muted">{job.detail}</p>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function WorkflowPanel() {
  const workflows = useVishnu((s) => s.workflows);
  const addWorkflow = useVishnu((s) => s.addWorkflow);
  const toggleWorkflow = useVishnu((s) => s.toggleWorkflow);
  const runWorkflow = useVishnu((s) => s.runWorkflow);
  const automations = useVishnu((s) => s.automations);
  const addAutomation = useVishnu((s) => s.addAutomation);
  const toggleAutomation = useVishnu((s) => s.toggleAutomation);
  const [name, setName] = useState("");
  const [steps, setSteps] = useState("inbox:Look at this\ntask:Do the next step");
  const [rule, setRule] = useState("");
  const [when, setWhen] = useState("");
  const [action, setAction] = useState("task:");
  return (
    <Page title="Workflows and automations" lede="A step starts with inbox: or task:. An automation fires only when a message you send contains its phrase.">
      <form
        className="grid gap-2 rounded-2xl border border-line bg-ink p-4"
        onSubmit={(e) => {
          e.preventDefault();
          addWorkflow(name, steps);
          setName("");
        }}
      >
        <h2 className="font-medium">Workflow</h2>
        <Field label="Name" value={name} onChange={setName} />
        <label className="text-sm text-muted">
          Steps
          <textarea value={steps} onChange={(e) => setSteps(e.target.value)} className="mt-1 min-h-20 w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-fg" />
        </label>
        <button type="submit" className="h-11 rounded-xl bg-accent text-sm font-medium text-accent-ink">Save workflow</button>
      </form>
      <ul className="mt-3 grid gap-2">
        {workflows.map((wf) => (
          <li key={wf.id} className="rounded-2xl border border-line p-4">
            <h3 className="font-medium">{wf.name}</h3>
            <p className="mt-1 text-sm text-muted">{wf.steps.join(" · ")}</p>
            <div className="mt-3 flex gap-2">
              <button type="button" onClick={() => runWorkflow(wf.id)} className="h-10 rounded-xl bg-accent px-3 text-sm font-medium text-accent-ink">Run</button>
              <button type="button" onClick={() => toggleWorkflow(wf.id)} className="h-10 rounded-xl border border-line px-3 text-sm">
                {wf.enabled ? "Disable" : "Enable"}
              </button>
            </div>
          </li>
        ))}
      </ul>
      <form
        className="mt-6 grid gap-2 rounded-2xl border border-line bg-ink p-4"
        onSubmit={(e) => {
          e.preventDefault();
          addAutomation(rule, when, action);
          setRule("");
          setWhen("");
        }}
      >
        <h2 className="font-medium">Automation</h2>
        <Field label="Name" value={rule} onChange={setRule} />
        <Field label="When a message contains" value={when} onChange={setWhen} />
        <Field label="Action (task: or inbox:)" value={action} onChange={setAction} />
        <button type="submit" className="h-11 rounded-xl border border-line text-sm">Save automation</button>
      </form>
      <ul className="mt-3 grid gap-2">
        {automations.map((ruleItem) => (
          <li key={ruleItem.id} className="flex items-center justify-between gap-3 rounded-xl border border-line px-3 py-2 text-sm">
            <span>{ruleItem.name}: “{ruleItem.when}” → {ruleItem.action}</span>
            <button type="button" onClick={() => toggleAutomation(ruleItem.id)} className="h-10 text-accent">
              {ruleItem.enabled ? "On" : "Off"}
            </button>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function AppsPanel() {
  const capabilities = useVishnu((s) => s.capabilities);
  const toggleCapability = useVishnu((s) => s.toggleCapability);
  const read = useOutsideRead();
  const live = [
    ["calendar", "Read calendar into Today"],
    ["mail", "Read mail into Inbox"],
    ["files", "Read Drive into Inbox"],
  ] as const;
  return (
    <Page title="Apps, tools, and capabilities" lede="Calendar, mail, and Drive are read from the account you connected in Grok. Nothing is sent. A missing connector asks you to connect it. High-risk switches only record that agents may use the result.">
      <div className="mb-4 flex flex-wrap gap-2">
        {live.map(([kind, label]) => (
          <button key={kind} type="button" onClick={() => void read(kind)} className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink">
            {label}
          </button>
        ))}
      </div>
      <ul className="grid gap-2">
        {capabilities.map((cap) => (
          <li key={cap.id} className="rounded-2xl border border-line bg-ink p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-medium">{cap.name}</h2>
                <p className="text-xs capitalize text-faint">{cap.kind} · {cap.risk} risk · {cap.connected ? "allowed" : "off"}</p>
                <p className="mt-1 text-sm text-muted">{cap.detail}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (cap.risk === "high" && !cap.connected && !window.confirm(`Allow ${cap.name}? Vishnu still will not send mail or change the calendar.`)) return;
                  toggleCapability(cap.id);
                }}
                className="h-10 rounded-xl border border-line px-3 text-sm"
              >
                {cap.connected ? "Disallow" : "Allow"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function AgentsPanel() {
  const agents = useVishnu((s) => s.agents);
  const briefAgent = useVishnu((s) => s.briefAgent);
  const addAgent = useVishnu((s) => s.addAgent);
  const [goal, setGoal] = useState("");
  const [agentId, setAgentId] = useState(agents[0]?.id ?? "");
  const [name, setName] = useState("");
  const [mandate, setMandate] = useState("");
  const read = useOutsideRead();
  return (
    <Page title="Agents" lede="A plan stays inside Vishnu. Reading calendar, mail, or Drive files the real items into Today or Inbox. Agents do not send mail or edit the calendar.">
      <form
        className="grid gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          briefAgent(agentId, goal);
          setGoal("");
          toast("Plan filed under Live work and Inbox.");
        }}
      >
        <select value={agentId} onChange={(e) => setAgentId(e.target.value)} aria-label="Agent" className="h-11 rounded-xl border border-line bg-ink px-3 text-sm">
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>{agent.name}</option>
          ))}
        </select>
        <Field label="Goal" value={goal} onChange={setGoal} placeholder="What should be planned?" />
        <button type="submit" className="h-11 rounded-xl bg-accent text-sm font-medium text-accent-ink">File a plan</button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={() => void read("calendar")} className="h-11 rounded-xl border border-line px-4 text-sm">
          Turn calendar into tasks
        </button>
        <button type="button" onClick={() => void read("mail")} className="h-11 rounded-xl border border-line px-4 text-sm">
          File mail into Inbox
        </button>
      </div>
      <form
        className="mt-4 grid gap-2 rounded-2xl border border-line p-4"
        onSubmit={(e) => {
          e.preventDefault();
          addAgent(name, mandate);
          setName("");
          setMandate("");
        }}
      >
        <h2 className="font-medium">New agent</h2>
        <Field label="Name" value={name} onChange={setName} />
        <Field label="Mandate" value={mandate} onChange={setMandate} placeholder="What this agent is allowed to plan" />
        <button type="submit" className="h-11 rounded-xl border border-line text-sm">Add agent</button>
      </form>
      <ul className="mt-4 grid gap-2">
        {agents.map((agent) => (
          <li key={agent.id} className="rounded-2xl border border-line p-4">
            <h2 className="font-medium">{agent.name}</h2>
            <p className="text-xs capitalize text-faint">{agent.status}</p>
            <p className="mt-1 text-sm text-muted">{agent.mandate}</p>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function CompanionPanel() {
  const devices = useVishnu((s) => s.devices);
  const redeemCode = useVishnu((s) => s.redeemCode);
  const sensorium = useVishnu((s) => s.sensorium);
  const [code, setCode] = useState("");
  return (
    <Page title="Phone companion" lede="Scan a waiting device code from Devices with the phone camera, or type it here. The handset must be signed into this same account. The screen that opens is this workspace, installed in the browser.">
      <div className="mx-auto max-w-sm rounded-3xl border border-line bg-ink p-4">
        <p className="text-xs tracking-[0.2em] text-faint">THIS DEVICE</p>
        <form
          className="mt-3 grid gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            toast(redeemCode(code));
            setCode("");
          }}
        >
          <Field label="Pairing code" value={code} onChange={setCode} placeholder="VISHNU-...." />
          <button type="submit" className="h-11 rounded-xl bg-accent text-sm font-medium text-accent-ink">Connect this device</button>
        </form>
        <ul className="mt-4 grid gap-2">
          {devices.map((device) => (
            <li key={device.id} className="text-sm">
              <span className="font-medium">{device.name}</span>
              <span className="text-faint"> · {device.revoked ? "revoked" : device.connected ? "connected" : "waiting"}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted">
          Sensing is {sensorium.stopped ? "stopped" : "following your Sensorium choices"}. The companion does not read the microphone unless you allow it there.
        </p>
      </div>
    </Page>
  );
}

export function DesktopPanel() {
  const setView = useVishnu((s) => s.setView);
  const jobs = useVishnu((s) => s.jobs);
  const inbox = useVishnu((s) => s.inbox);
  const devices = useVishnu((s) => s.devices);
  const vault = useVishnu((s) => s.vault);
  const tasks = useVishnu((s) => s.tasks);
  const memories = useVishnu((s) => s.memories);
  const addTask = useVishnu((s) => s.addTask);
  const [task, setTask] = useState("");
  const cards = [
    ["Live work", `${jobs.filter((j) => j.status !== "done").length} open`, "live"],
    ["Inbox", `${inbox.filter((i) => !i.read).length} unread`, "inbox"],
    ["Today", `${tasks.filter((item) => !item.done).length} open tasks`, "today"],
    ["Memory", `${memories.length} stored`, "memory"],
    ["Graph", "See how memories connect", "graph"],
    ["Devices", `${devices.filter((d) => d.connected && !d.revoked).length} connected`, "devices"],
    ["Vault", vault ? "Sealed" : "Empty", "vault"],
    ["Phone", "Enter a pairing code", "companion"],
  ] as const;
  return (
    <Page title="Desktop console" lede="The owner desk for this browser. It uses the same workspace as the phone companion. It is not a separate installable application.">
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          addTask(task);
          setTask("");
        }}
      >
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Capture a task from the desk"
          aria-label="Desk task"
          className="h-11 flex-1 rounded-xl border border-line bg-ink px-3 text-base outline-none"
        />
        <button type="submit" className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink">Add</button>
      </form>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {cards.map(([title, detail, view]) => (
          <button key={title} type="button" onClick={() => setView(view)} className="rounded-2xl border border-line bg-ink p-4 text-left hover:border-accent">
            <span className="block font-medium">{title}</span>
            <span className="mt-1 block text-sm text-muted">{detail}</span>
          </button>
        ))}
      </div>
    </Page>
  );
}

export function VaultPanel() {
  const vault = useVishnu((s) => s.vault);
  const setVault = useVishnu((s) => s.setVault);
  const [passphrase, setPassphrase] = useState("");
  const [secrets, setSecrets] = useState<Secret[] | null>(null);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  async function unlock(event: FormEvent) {
    event.preventDefault();
    if (!vault) {
      setSecrets([]);
      return;
    }
    setBusy(true);
    try {
      setSecrets(await openVault(passphrase, vault));
      toast("Vault open. The passphrase stays in this tab.");
    } catch {
      toast("That passphrase does not open the vault.");
    } finally {
      setBusy(false);
    }
  }

  async function save(next: Secret[]) {
    if (passphrase.length < 8) {
      toast("Use a passphrase of at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      setVault(await sealVault(passphrase, next));
      setSecrets(next);
      toast("Sealed. The server stores ciphertext only.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Encrypted vault" lede="Secrets are sealed in this browser with AES-GCM. The key is derived from your passphrase with PBKDF2, 600,000 rounds, SHA-256. The passphrase is never saved or sent.">
      <form onSubmit={unlock} className="grid gap-2">
        <Field label="Vault passphrase" value={passphrase} onChange={setPassphrase} type="password" />
        <button type="submit" disabled={busy} className="h-11 rounded-xl bg-accent text-sm font-medium text-accent-ink disabled:opacity-40">
          {busy ? "Working…" : vault ? "Unlock" : "Start a new vault"}
        </button>
      </form>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        Web Crypto has no Argon2id, so the key is PBKDF2-HMAC-SHA256 at 600,000 iterations, the OWASP 2023 minimum, then AES-256-GCM with a fresh 16-byte salt and 12-byte IV. Only the ciphertext is synced. A wrong passphrase fails to decrypt and reveals nothing.
      </p>
      {secrets && (
        <form
          className="mt-4 grid gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim() || !value.trim()) return;
            const next = [{ id: crypto.randomUUID(), name: name.trim(), value: value.trim() }, ...secrets];
            setName("");
            setValue("");
            void save(next);
          }}
        >
          <div className="flex items-center justify-between">
            <h2 className="font-medium">Open secrets</h2>
            <button
              type="button"
              className="h-10 text-sm text-accent"
              onClick={() => {
                setSecrets(null);
                setPassphrase("");
                setName("");
                setValue("");
              }}
            >
              Lock
            </button>
          </div>
          <Field label="Secret name" value={name} onChange={setName} />
          <Field label="Secret value" value={value} onChange={setValue} type="password" />
          <button type="submit" disabled={busy} className="h-11 rounded-xl border border-line text-sm">Seal secret</button>
          <ul className="mt-2 grid gap-2">
            {secrets.map((secret) => (
              <li key={secret.id} className="rounded-xl border border-line p-3">
                <p className="font-medium">{secret.name}</p>
                <p className="mt-1 break-all text-sm text-muted">{secret.value}</p>
                <button
                  type="button"
                  className="mt-2 h-10 text-sm text-danger"
                  onClick={() => void save(secrets.filter((item) => item.id !== secret.id))}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </form>
      )}
      {!secrets && vault && (
        <p className="mt-3 text-sm text-muted">
          Vault is sealed{vault.updatedAt ? ` as of ${new Date(vault.updatedAt).toLocaleString()}` : ""}. Names stay hidden until you unlock.
        </p>
      )}
    </Page>
  );
}

export function SensoriumPanel() {
  const sensorium = useVishnu((s) => s.sensorium);
  const setSensor = useVishnu((s) => s.setSensor);
  const stopSensing = useVishnu((s) => s.stopSensing);
  const rows = [
    ["microphone", "Microphone"],
    ["screen", "Screen"],
    ["location", "Location"],
    ["notifications", "Notifications"],
  ] as const;

  async function allow(key: (typeof rows)[number][0], label: string) {
    if (sensorium[key]) {
      setSensor({ [key]: false });
      return;
    }
    try {
      if (key === "microphone") {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
      } else if (key === "screen") {
        const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        stream.getTracks().forEach((track) => track.stop());
      } else if (key === "location") {
        await new Promise<void>((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(() => resolve(), () => reject(new Error("denied")), { timeout: 8000 });
        });
      } else {
        const permission = await Notification.requestPermission();
        if (permission !== "granted") throw new Error("denied");
      }
      setSensor({ [key]: true });
      toast(`${label} is allowed in this browser.`);
    } catch {
      toast(`This browser did not allow ${label.toLowerCase()}.`);
    }
  }

  return (
    <Page title="Sensorium" lede="These switches only govern this browser. They do not turn on a phone camera or a desktop screen capture.">
      <ul className="divide-y divide-line rounded-2xl border border-line">
        {rows.map(([key, label]) => (
          <li key={key} className="flex items-center justify-between px-4 py-3">
            <span className="text-sm">{label}</span>
            <button
              type="button"
              role="switch"
              aria-checked={sensorium[key]}
              onClick={() => void allow(key, label)}
              className={sensorium[key] ? "h-10 rounded-full bg-accent px-3 text-sm text-accent-ink" : "h-10 rounded-full border border-line px-3 text-sm"}
            >
              {sensorium[key] ? "On" : "Off"}
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={stopSensing} className="mt-4 h-11 rounded-xl border border-danger px-4 text-sm text-danger">
        Stop all sensing
      </button>
    </Page>
  );
}

export function SystemPanel() {
  const owner = useVishnu((s) => s.owner);
  const settings = useVishnu((s) => s.settings);
  const devices = useVishnu((s) => s.devices);
  const vault = useVishnu((s) => s.vault);
  const memories = useVishnu((s) => s.memories);
  const knowledge = useVishnu((s) => s.knowledge);
  const links = useVishnu((s) => s.links);
  const jobs = useVishnu((s) => s.jobs);
  const syncState = useVishnu((s) => s.syncState);
  const activity = useVishnu((s) => s.activity);
  const connected = devices.filter((d) => d.connected && !d.revoked).length;
  const waiting = devices.filter((d) => !d.connected && !d.revoked).length;
  return (
    <Page title="System, status, and updates" lede="Install this workspace on a computer, Android, or iPhone. A published update replaces the build. The account is the same one on every screen.">
      <dl className="divide-y divide-line rounded-2xl border border-line bg-ink">
        {[
          ["Owner", owner?.name ?? "Not set"],
          ["Autonomy", settings.autonomy],
          ["Emergency stop", settings.emergency ? "On" : "Off"],
          ["Sync", syncState === "offline" ? "Offline. Local copy kept." : "Account copy ready"],
          ["Connected devices", String(connected)],
          ["Waiting to pair", String(waiting)],
          ["Memories", `${memories.length} · ${links.length} links`],
          ["Knowledge sources", String(knowledge.length)],
          ["Live jobs", String(jobs.length)],
          ["Vault", vault ? "Sealed ciphertext stored" : "No secrets yet"],
          ["Last event", activity[0] ? `${activity[0].detail}` : "None"],
          ["Channel", "Browser workspace 2026.11"],
          ["Updater", "Not connected. Publish replaces this build."],
          ["Sign-in", "Google, X, email, passkey, or a recovery code"],
        ].map(([key, value]) => (
          <div key={key} className="flex items-start justify-between gap-4 px-4 py-3">
            <dt className="text-sm text-muted">{key}</dt>
            <dd className="max-w-[60%] text-right text-sm break-words">{value}</dd>
          </div>
        ))}
      </dl>
      <InstallActions />
    </Page>
  );
}
