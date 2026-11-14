import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { useVishnu } from "@/lib/vishnu/store";
import type { View } from "@/lib/vishnu/types";

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

export function DashboardPanel() {
  const setView = useVishnu((s) => s.setView);
  const memories = useVishnu((s) => s.memories);
  const devices = useVishnu((s) => s.devices);
  const jobs = useVishnu((s) => s.jobs);
  const vault = useVishnu((s) => s.vault);
  const settings = useVishnu((s) => s.settings);
  const products = useVishnu((s) => s.products);
  const cards: { label: string; value: string; view: View }[] = [
    { label: "Memory", value: String(memories.length), view: "memory" },
    { label: "Devices", value: String(devices.filter((d) => d.connected && !d.revoked).length), view: "devices" },
    { label: "Voice", value: settings.voice ? "On" : "Off", view: "voice" },
    { label: "Security", value: vault ? "Vault sealed" : "No vault yet", view: "vault" },
    { label: "Live work", value: String(jobs.length), view: "live" },
    { label: "Recovery", value: settings.storageSync ? "Account copy on" : "This browser only", view: "storage" },
    { label: "Products", value: String(products.length), view: "products" },
    { label: "Model", value: settings.model === "local" ? "Local brain" : "Cloud mind", view: "models" },
  ];
  return (
    <Page title="Dashboard" lede="The control view from the desktop app: memory, devices, voice, security, live work, and recovery. Each card opens that section.">
      <ul className="grid gap-3 sm:grid-cols-2">
        {cards.map((card) => (
          <li key={card.label}>
            <button type="button" onClick={() => setView(card.view)} className="w-full rounded-2xl border border-line bg-ink p-4 text-left">
              <p className="text-xs text-faint">{card.label}</p>
              <p className="mt-1 font-medium">{card.value}</p>
            </button>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function ProductsPanel() {
  const products = useVishnu((s) => s.products);
  const projects = useVishnu((s) => s.projects);
  const addProduct = useVishnu((s) => s.addProduct);
  const deleteProduct = useVishnu((s) => s.deleteProduct);
  const [name, setName] = useState("");
  const [audience, setAudience] = useState("");
  const [promise, setPromise] = useState("");
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [openId, setOpenId] = useState<string | null>(null);
  const open = products.find((item) => item.id === openId) ?? null;

  return (
    <Page title="Our products" lede="A product is a named offer you keep here. Convert a project to start one. The manifest is the record. It does not publish a store app.">
      <form
        className="grid gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          addProduct({ name, audience, promise });
          setName("");
          setAudience("");
          setPromise("");
          toast("Product created.");
        }}
      >
        <Field label="Name" value={name} onChange={setName} placeholder="What it is called" />
        <Field label="Who it is for" value={audience} onChange={setAudience} />
        <Field label="Promise" value={promise} onChange={setPromise} placeholder="What it does for them" />
        <button type="submit" className="h-11 rounded-xl bg-accent text-sm font-medium text-accent-ink">Create product</button>
      </form>
      <form
        className="mt-4 flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          const project = projects.find((item) => item.id === projectId);
          if (!project) {
            toast("Create a project first.");
            return;
          }
          addProduct({ name: project.title, audience: "From a project", promise: project.intent || project.next, sourceProjectId: project.id });
          toast(`Converted ${project.title}.`);
        }}
      >
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)} aria-label="Project" className="h-11 flex-1 rounded-xl border border-line bg-ink px-3 text-sm">
          {projects.length === 0 && <option value="">No projects yet</option>}
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.title}</option>
          ))}
        </select>
        <button type="submit" className="h-11 rounded-xl border border-line px-4 text-sm">Import from project</button>
      </form>
      <ul className="mt-4 grid gap-2">
        {products.map((product) => (
          <li key={product.id} className="rounded-2xl border border-line bg-ink p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-medium">{product.name}</h2>
                <p className="text-sm text-muted">{product.audience || "No audience yet"}</p>
              </div>
              <button type="button" onClick={() => setOpenId(openId === product.id ? null : product.id)} className="h-10 text-sm text-accent">
                {openId === product.id ? "Close" : "Open"}
              </button>
            </div>
            {open?.id === product.id && (
              <div className="mt-3">
                <p className="text-sm">{product.promise || "No promise written."}</p>
                <pre className="mt-3 overflow-x-auto rounded-xl bg-bg p-3 text-xs text-muted">{JSON.stringify({ name: product.name, audience: product.audience, promise: product.promise, sourceProjectId: product.sourceProjectId ?? null }, null, 2)}</pre>
                <button type="button" onClick={() => deleteProduct(product.id)} className="mt-2 h-10 text-sm text-danger">Remove</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function StoragePanel() {
  const settings = useVishnu((s) => s.settings);
  const setStorageSync = useVishnu((s) => s.setStorageSync);
  const vault = useVishnu((s) => s.vault);
  return (
    <Page title="Data and cloud storage" lede="This browser always keeps a copy. The signed-in account is the only remote copy. There is no second cloud drive.">
      <button
        type="button"
        role="switch"
        aria-checked={settings.storageSync}
        onClick={() => setStorageSync(!settings.storageSync)}
        className={settings.storageSync ? "h-11 rounded-full bg-accent px-4 text-sm text-accent-ink" : "h-11 rounded-full border border-line px-4 text-sm"}
      >
        {settings.storageSync ? "Account sync on" : "Account sync off"}
      </button>
      <ul className="mt-4 grid gap-2 text-sm text-muted">
        <li className="rounded-2xl border border-line px-4 py-3">Browser copy: on. Closing the tab does not delete it.</li>
        <li className="rounded-2xl border border-line px-4 py-3">{settings.storageSync ? "New changes upload to this account." : "New changes stay here until you turn sync back on."}</li>
        <li className="rounded-2xl border border-line px-4 py-3">Vault: {vault ? "ciphertext only. The passphrase is not stored." : "empty."}</li>
      </ul>
    </Page>
  );
}

export function VoicePanel() {
  const settings = useVishnu((s) => s.settings);
  const setVoice = useVishnu((s) => s.setVoice);
  const setVoiceRate = useVishnu((s) => s.setVoiceRate);
  const setVoicePitch = useVishnu((s) => s.setVoicePitch);
  const setDraft = useVishnu((s) => s.setDraft);
  const setView = useVishnu((s) => s.setView);
  const [heard, setHeard] = useState("");

  return (
    <Page title="Voice studio" lede="Speak replies uses this browser’s voice. A listen test types into Home. Phone calls are not placed from here.">
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => setVoice(!settings.voice)} className="h-11 rounded-xl border border-line px-4 text-sm">
          {settings.voice ? "Speak replies: on" : "Speak replies: off"}
        </button>
        <button
          type="button"
          className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink"
          onClick={() => {
            if (!("speechSynthesis" in window)) {
              toast("This browser has no speech voice.");
              return;
            }
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance("Vishnu is listening on this browser.");
            utter.rate = settings.voiceRate || 1;
            utter.pitch = settings.voicePitch || 1;
            window.speechSynthesis.speak(utter);
          }}
        >
          Test voice
        </button>
        <button
          type="button"
          className="h-11 rounded-xl border border-line px-4 text-sm"
          onClick={() => {
            const host = window as unknown as {
              SpeechRecognition?: new () => SpeechRec;
              webkitSpeechRecognition?: new () => SpeechRec;
            };
            const Ctor = host.SpeechRecognition || host.webkitSpeechRecognition;
            if (!Ctor) {
              toast("This browser cannot dictate.");
              return;
            }
            const rec = new Ctor();
            rec.lang = "en-US";
            rec.onresult = (event) => {
              const text = event.results[0]?.[0]?.transcript ?? "";
              setHeard(text);
              setDraft(text);
              toast("Heard. It is waiting in Home.");
            };
            rec.onerror = () => toast("Could not hear. Allow the microphone and try again.");
            rec.start();
          }}
        >
          Listen once
        </button>
      </div>
      <label className="mt-4 block text-sm text-muted">
        Rate {settings.voiceRate.toFixed(1)}
        <input type="range" min={0.6} max={1.4} step={0.1} value={settings.voiceRate} onChange={(e) => setVoiceRate(Number(e.target.value))} className="mt-1 w-full" />
      </label>
      <label className="mt-3 block text-sm text-muted">
        Pitch {settings.voicePitch.toFixed(1)}
        <input type="range" min={0.6} max={1.4} step={0.1} value={settings.voicePitch} onChange={(e) => setVoicePitch(Number(e.target.value))} className="mt-1 w-full" />
      </label>
      {heard && <p className="mt-4 text-sm">Last heard: {heard}</p>}
      <button type="button" onClick={() => setView("home")} className="mt-4 h-10 text-sm text-accent">Open Home with that text</button>
    </Page>
  );
}

type SpeechRec = {
  lang: string;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  start: () => void;
};

export function ApprovalsPanel() {
  const conversations = useVishnu((s) => s.conversations);
  const applyProposal = useVishnu((s) => s.applyProposal);
  const setActionStatus = useVishnu((s) => s.setActionStatus);
  const pending = conversations.flatMap((conversation) =>
    conversation.messages.flatMap((message) =>
      (message.actions ?? [])
        .filter((action) => action.status === "pending")
        .map((action) => ({ action, conversationId: conversation.id, messageId: message.id })),
    ),
  );
  return (
    <Page title="Approvals" lede="When autonomy is Suggest or Ask, a proposed memory, task, or note waits here and on the message. Nothing is written until you accept it. Observe never proposes a write. Act writes low-risk items immediately.">
      {pending.length === 0 ? (
        <p className="text-sm text-muted">Nothing is waiting.</p>
      ) : (
        <ul className="grid gap-2">
          {pending.map(({ action, conversationId, messageId }) => (
            <li key={action.id} className="rounded-2xl border border-line bg-ink p-4">
              <p className="text-xs capitalize text-faint">{action.proposal.type}</p>
              <p className="mt-1 text-sm">{action.proposal.title}</p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  className="h-10 rounded-xl bg-accent px-3 text-sm font-medium text-accent-ink"
                  onClick={() => {
                    const detail = applyProposal(action.proposal);
                    setActionStatus(conversationId, messageId, action.id, "applied");
                    toast(detail);
                  }}
                >
                  Accept
                </button>
                <button type="button" className="h-10 rounded-xl border border-line px-3 text-sm" onClick={() => setActionStatus(conversationId, messageId, action.id, "dismissed")}>
                  Dismiss
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Page>
  );
}

export function NotificationsPanel() {
  const activity = useVishnu((s) => s.activity);
  const dismissed = useVishnu((s) => s.dismissedNotices);
  const dismissNotice = useVishnu((s) => s.dismissNotice);
  const items = activity.filter((item) => !dismissed.includes(item.id)).slice(0, 30);
  return (
    <Page title="Notifications" lede="These are events Vishnu already recorded: sync, devices, products, voice, and the rest. Dismiss hides one here. It does not delete the activity log.">
      {items.length === 0 ? (
        <p className="text-sm text-muted">No notices.</p>
      ) : (
        <ul className="grid gap-2">
          {items.map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-3 rounded-2xl border border-line px-4 py-3">
              <div>
                <p className="text-xs capitalize text-faint">{item.kind}</p>
                <p className="text-sm">{item.detail}</p>
              </div>
              <button type="button" onClick={() => dismissNotice(item.id)} className="h-10 shrink-0 text-sm text-accent">Dismiss</button>
            </li>
          ))}
        </ul>
      )}
    </Page>
  );
}

export function ModelsPanel() {
  const model = useVishnu((s) => s.settings.model);
  const setModel = useVishnu((s) => s.setModel);
  return (
    <Page title="Models" lede="Cloud mind uses the signed-in account’s model when you send a message. Local brain answers on this page and never calls out. There is no separate model server to install.">
      <div className="grid gap-2">
        {([
          ["cloud", "Cloud mind", "Send messages to the cloud mind. If it fails, the local brain answers."],
          ["local", "Local brain", "Do not call the cloud mind. Answers stay in this browser."],
        ] as const).map(([id, title, body]) => (
          <button key={id} type="button" onClick={() => setModel(id)} className={model === id ? "rounded-2xl border border-accent bg-panel px-4 py-3 text-left" : "rounded-2xl border border-line bg-ink px-4 py-3 text-left"}>
            <span className="block font-medium">{title}</span>
            <span className="mt-1 block text-sm text-muted">{body}</span>
          </button>
        ))}
      </div>
    </Page>
  );
}

export function RelationshipsPanel() {
  const memories = useVishnu((s) => s.memories);
  const links = useVishnu((s) => s.links);
  const people = memories.filter((item) => item.kind === "person");
  return (
    <Page title="Relationships" lede="People you saved as memory, and the links you drew on the graph. A relationship exists only when both sides are in memory.">
      {people.length === 0 ? <p className="text-sm text-muted">No people yet. Add one under Memory with kind Person.</p> : null}
      <ul className="grid gap-2">
        {people.map((person) => {
          const related = links.filter((link) => link.fromId === person.id || link.toId === person.id);
          return (
            <li key={person.id} className="rounded-2xl border border-line bg-ink p-4">
              <h2 className="font-medium">{person.title}</h2>
              <p className="text-sm text-muted">{person.body}</p>
              <ul className="mt-2 text-sm text-faint">
                {related.length === 0 && <li>No links yet.</li>}
                {related.map((link) => {
                  const otherId = link.fromId === person.id ? link.toId : link.fromId;
                  const other = memories.find((item) => item.id === otherId);
                  return <li key={link.id}>{link.label}: {other?.title ?? "Missing memory"}</li>;
                })}
              </ul>
            </li>
          );
        })}
      </ul>
    </Page>
  );
}

export function ExtensionsPanel() {
  const extensions = useVishnu((s) => s.extensions);
  const addExtension = useVishnu((s) => s.addExtension);
  const toggleExtension = useVishnu((s) => s.toggleExtension);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  return (
    <Page title="Extensions" lede="Record an extension you intend to use. Vishnu does not download or run plugin code from the original repository. Turning one on only marks it allowed in this workspace.">
      <form
        className="grid gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          addExtension(name, note);
          setName("");
          setNote("");
        }}
      >
        <Field label="Name" value={name} onChange={setName} />
        <Field label="Note" value={note} onChange={setNote} placeholder="What you want it for" />
        <button type="submit" className="h-11 rounded-xl border border-line text-sm">Record extension</button>
      </form>
      <ul className="mt-4 grid gap-2">
        {extensions.map((item) => (
          <li key={item.id} className="flex items-start justify-between gap-3 rounded-2xl border border-line px-4 py-3">
            <div>
              <h2 className="font-medium">{item.name}</h2>
              <p className="text-sm text-muted">{item.note}</p>
            </div>
            <button type="button" onClick={() => toggleExtension(item.id)} className="h-10 text-sm text-accent">
              {item.enabled ? "Allowed" : "Off"}
            </button>
          </li>
        ))}
      </ul>
    </Page>
  );
}
