import { useEffect, useRef, useState } from "react";
import { ArrowUp, Mic, SquarePen } from "lucide-react";
import { toast } from "sonner";
import { askVishnu } from "@/lib/vishnu/ask";
import { buildPayload, localAnswer, shouldAutoApply } from "@/lib/vishnu/brain";
import { activeConversation, useVishnu } from "@/lib/vishnu/store";
import type { ChatAction, ChatMessage, Proposal } from "@/lib/vishnu/types";
import { NeuralCore } from "./core";
import { cn } from "@/lib/cn";

function uid(prefix: string) {
  return `${prefix}_${crypto.randomUUID()}`;
}

function speak(text: string) {
  if (!("speechSynthesis" in window)) return;
  const settings = useVishnu.getState().settings;
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text.slice(0, 500));
  utter.rate = settings.voiceRate || 1;
  utter.pitch = settings.voicePitch || 1;
  window.speechSynthesis.speak(utter);
}

type Rec = {
  lang: string;
  interimResults: boolean;
  onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function recognition(): Rec | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => Rec;
    webkitSpeechRecognition?: new () => Rec;
  };
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = "en-US";
  rec.interimResults = false;
  return rec;
}

function greeting(name: string) {
  const h = new Date().getHours();
  const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  return `${part}, ${name}`;
}

const STARTERS = [
  "Remember that I prefer short, direct answers.",
  "Remind me to review open tasks tomorrow.",
  "What should I pay attention to today?",
  "What do you remember about me?",
];

export function Home() {
  const data = useVishnu();
  const conversation = activeConversation(data);
  const [pending, setPending] = useState(false);
  const [listening, setListening] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const recRef = useRef<Rec | null>(null);
  const messages = conversation?.messages ?? [];

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, pending]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || pending || !conversation) return;
    data.setDraft("");
    const userMessage: ChatMessage = {
      id: uid("msg"),
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };
    data.appendMessage(conversation.id, userMessage);
    data.touchBrowser();
    data.runAutomations(content);
    setPending(true);
    const history = [...conversation.messages, userMessage].map((m) => ({
      role: m.role,
      content: m.content,
    }));
    const snapshot = useVishnu.getState();
    let textOut = "";
    let actions: Proposal[] = [];
    let source: "model" | "local" = "local";
    if (snapshot.settings.model === "local") {
      const local = localAnswer(snapshot, content);
      textOut = local.text;
      actions = local.actions;
    } else {
      try {
        const remote = await askVishnu({ data: buildPayload(snapshot, history) });
        if (remote.ok) {
          textOut = remote.text;
          actions = remote.actions;
          source = "model";
        } else {
          const local = localAnswer(snapshot, content);
          textOut = local.text;
          actions = local.actions;
          if (!remote.error.includes("not available")) {
            textOut = `${local.text}\n\nCloud mind didn’t answer (${remote.error}).`;
          }
        }
      } catch (error) {
        const local = localAnswer(snapshot, content);
        textOut = local.text;
        actions = local.actions;
        const message = error instanceof Error ? error.message : "Request failed";
        textOut = `${local.text}\n\nCloud mind didn’t answer (${message}).`;
      }
    }

    const fresh = useVishnu.getState();
    const chatActions: ChatAction[] = actions.map((proposal) => {
      const id = uid("actn");
      if (shouldAutoApply(fresh.settings.autonomy, proposal, fresh.settings.emergency)) {
        fresh.applyProposal(proposal);
        return { id, proposal, status: "applied" as const };
      }
      return { id, proposal, status: "pending" as const };
    });

    const assistant: ChatMessage = {
      id: uid("msg"),
      role: "assistant",
      content: textOut,
      createdAt: new Date().toISOString(),
      actions: chatActions,
      source,
    };
    useVishnu.getState().appendMessage(conversation.id, assistant);
    if (useVishnu.getState().settings.voice) speak(textOut);
    setPending(false);
  }

  function decide(messageId: string, action: ChatAction, accept: boolean) {
    if (!conversation || action.status !== "pending") return;
    if (!accept) {
      data.setActionStatus(conversation.id, messageId, action.id, "dismissed");
      return;
    }
    if (data.settings.emergency) {
      toast("Emergency stop is on. Lift it in Settings to write.");
      return;
    }
    const detail = data.applyProposal(action.proposal);
    data.setActionStatus(conversation.id, messageId, action.id, "applied");
    toast(detail);
  }

  function onMic() {
    const sense = useVishnu.getState().sensorium;
    if (sense.stopped || !sense.microphone) {
      toast("Turn the microphone on in Sensorium before listening.");
      return;
    }
    if (listening) {
      recRef.current?.stop();
      setListening(false);
      return;
    }
    const rec = recognition();
    if (!rec) {
      toast("This browser has no speech recognition.");
      return;
    }
    rec.onresult = (ev) => {
      const said = ev.results[0]?.[0]?.transcript ?? "";
      if (said) data.setDraft(said);
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      toast("Microphone didn’t start.");
      setListening(false);
    }
  }

  const empty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scroller} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-8">
        {empty ? (
          <div className="mx-auto flex max-w-xl flex-col items-center pt-4">
            <NeuralCore active={pending || listening} />
            <h1 className="text-center text-3xl font-medium tracking-tight">
              {data.owner ? greeting(data.owner.name) : "Vishnu"}
            </h1>
            <p className="mt-2 max-w-md text-center text-sm leading-relaxed text-muted">
              I keep what you tell me, and this account can open the same workspace on another browser. Ask freely, or tell me to remember, remind, or file a note.
            </p>
            <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
              {STARTERS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => data.setDraft(prompt)}
                  className="rounded-2xl border border-line bg-ink px-4 py-3 text-left text-sm leading-snug text-fg hover:border-accent"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-3">
            <div className="mb-2">
              <NeuralCore active={pending || listening} size="sm" />
            </div>
            {messages.map((message) => (
              <article
                key={message.id}
                className={cn(
                  "max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap",
                  message.role === "user"
                    ? "self-end bg-panel text-fg"
                    : "self-start border border-line bg-ink text-fg",
                )}
              >
                {message.content}
                {message.role === "assistant" && message.source && (
                  <p className="mt-2 text-xs text-faint">
                    {message.source === "model" ? "Cloud mind" : "This device"}
                  </p>
                )}
                {message.actions?.map((action) => (
                  <div key={action.id} className="mt-3 rounded-xl border border-line bg-bg px-3 py-2">
                    <p className="text-xs text-muted">{labelFor(action.proposal)}</p>
                    <p className="mt-1 text-sm">{summary(action.proposal)}</p>
                    {action.status === "pending" ? (
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button"
                          onClick={() => decide(message.id, action, true)}
                          className="h-10 rounded-xl bg-accent px-3 text-sm font-medium text-accent-ink"
                        >
                          Keep
                        </button>
                        <button
                          type="button"
                          onClick={() => decide(message.id, action, false)}
                          className="h-10 rounded-xl border border-line px-3 text-sm"
                        >
                          Dismiss
                        </button>
                      </div>
                    ) : (
                      <p className="mt-2 text-xs capitalize text-faint">{action.status}</p>
                    )}
                  </div>
                ))}
              </article>
            ))}
            {pending && <p className="text-sm text-muted">Thinking…</p>}
          </div>
        )}
      </div>

      <form
        className="border-t border-line px-4 py-3 sm:px-8"
        onSubmit={(e) => {
          e.preventDefault();
          void send(data.composerDraft);
        }}
      >
        <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-3xl border border-line bg-ink px-2 py-2">
          <button
            type="button"
            onClick={() => data.newChat()}
            className="grid size-11 shrink-0 place-items-center rounded-full text-muted hover:text-fg"
            aria-label="New conversation"
          >
            <SquarePen className="size-5" />
          </button>
          <label className="sr-only" htmlFor="composer">
            Message Vishnu
          </label>
          <textarea
            id="composer"
            rows={1}
            value={data.composerDraft}
            onChange={(e) => data.setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(data.composerDraft);
              }
            }}
            placeholder="Talk with Vishnu"
            className="max-h-36 min-h-11 flex-1 resize-none bg-transparent py-2.5 text-base outline-none"
          />
          <button
            type="button"
            onClick={onMic}
            aria-pressed={listening}
            aria-label={listening ? "Stop listening" : "Speak"}
            className={cn(
              "grid size-11 shrink-0 place-items-center rounded-full border border-line",
              listening ? "bg-accent text-accent-ink" : "text-muted",
            )}
          >
            <Mic className="size-5" />
          </button>
          <button
            type="submit"
            disabled={pending || !data.composerDraft.trim()}
            aria-label="Send"
            className="grid size-11 shrink-0 place-items-center rounded-full bg-accent text-accent-ink disabled:opacity-40"
          >
            <ArrowUp className="size-5" />
          </button>
        </div>
      </form>
    </div>
  );
}

function labelFor(proposal: Proposal) {
  if (proposal.type === "remember") return "Memory";
  if (proposal.type === "task") return "Task";
  if (proposal.type === "knowledge") return "Knowledge";
  return "Forget";
}

function summary(proposal: Proposal) {
  if (proposal.type === "remember") return `${proposal.title} — ${proposal.body}`;
  if (proposal.type === "task") return proposal.due ? `${proposal.title} · ${proposal.due}` : proposal.title;
  if (proposal.type === "knowledge") return proposal.title;
  return proposal.title;
}
