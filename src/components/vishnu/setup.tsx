import { useMemo, useState } from "react";
import { pairingCode, useVishnu } from "@/lib/vishnu/store";
import type { Autonomy } from "@/lib/vishnu/types";
import { NeuralCore } from "./core";
import { cn } from "@/lib/cn";

const AUTONOMY: { id: Autonomy; title: string; body: string }[] = [
  { id: "observe", title: "Observe", body: "Answer only. Never write unless you do it yourself." },
  { id: "suggest", title: "Suggest", body: "Propose memories and tasks. Nothing is saved until you accept." },
  { id: "ask", title: "Ask", body: "Same as suggest, with a clear confirm step. Recommended." },
  { id: "act", title: "Act", body: "Low-risk saves happen immediately. Deletes still wait for you." },
];

export function Setup() {
  const completeSetup = useVishnu((s) => s.completeSetup);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [autonomy, setAutonomy] = useState<Autonomy>("ask");
  const [ack, setAck] = useState(false);
  const codes = useMemo(() => Array.from({ length: 8 }, () => pairingCode()), []);

  const next = () => setStep((n) => n + 1);

  return (
    <main className="app-frame flex items-center justify-center overflow-auto bg-bg px-4 py-8">
      <section className="w-full max-w-lg">
        <div className="mb-2">
          <NeuralCore size="sm" />
        </div>
        <p className="text-center text-xs font-medium tracking-[0.28em] text-muted">VISHNU</p>
        <p className="mt-2 text-center text-sm text-faint">Step {step + 1} of 5</p>

        {step === 0 && (
          <div className="mt-6">
            <h1 className="text-center text-3xl font-medium tracking-tight">Create your Vishnu</h1>
            <p className="mt-3 text-center text-base leading-relaxed text-muted">
              One owner. Conversation, memory, knowledge, and tasks sync to the account you signed in with.
              The cloud mind runs only when you send a message. The vault passphrase never leaves this tab.
            </p>
            <button
              type="button"
              onClick={next}
              className="mt-8 h-12 w-full rounded-2xl bg-accent font-medium text-accent-ink"
            >
              Begin
            </button>
          </div>
        )}

        {step === 1 && (
          <form
            className="mt-6"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) next();
            }}
          >
            <h1 className="text-2xl font-medium">What should I call you?</h1>
            <p className="mt-2 text-sm text-muted">This is the name on your workspace, not an account.</p>
            <label className="mt-6 block text-sm text-muted" htmlFor="owner-name">
              Owner name
            </label>
            <input
              id="owner-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              maxLength={60}
              className="mt-2 h-12 w-full rounded-2xl border border-line bg-ink px-4 text-base text-fg outline-none"
              placeholder="Your name"
            />
            <button
              type="submit"
              disabled={!name.trim()}
              className="mt-6 h-12 w-full rounded-2xl bg-accent font-medium text-accent-ink disabled:opacity-40"
            >
              Continue
            </button>
          </form>
        )}

        {step === 2 && (
          <div className="mt-6">
            <h1 className="text-2xl font-medium">How should I act?</h1>
            <p className="mt-2 text-sm text-muted">You can change this later in Settings.</p>
            <div className="mt-5 grid gap-2">
              {AUTONOMY.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setAutonomy(item.id)}
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-left",
                    autonomy === item.id ? "border-accent bg-panel" : "border-line bg-ink",
                  )}
                >
                  <span className="block font-medium">{item.title}</span>
                  <span className="mt-1 block text-sm text-muted">{item.body}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={next}
              className="mt-6 h-12 w-full rounded-2xl bg-accent font-medium text-accent-ink"
            >
              Continue
            </button>
          </div>
        )}

        {step === 3 && (
          <div className="mt-6">
            <h1 className="text-2xl font-medium">Save your recovery codes</h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              These identify this workspace if you export it. They live in this browser, not in an encrypted vault.
              Copy them somewhere private.
            </p>
            <ul className="mt-4 grid grid-cols-1 gap-2 rounded-2xl border border-line bg-ink p-4 sm:grid-cols-2">
              {codes.map((code) => (
                <li key={code} className="font-mono text-sm tracking-wide text-accent">
                  {code}
                </li>
              ))}
            </ul>
            <label className="mt-4 flex items-start gap-3 text-sm text-muted">
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
                className="mt-1 size-4"
              />
              I saved these codes.
            </label>
            <button
              type="button"
              disabled={!ack}
              onClick={next}
              className="mt-6 h-12 w-full rounded-2xl bg-accent font-medium text-accent-ink disabled:opacity-40"
            >
              Review
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="mt-6">
            <h1 className="text-2xl font-medium">Review</h1>
            <dl className="mt-4 divide-y divide-line rounded-2xl border border-line bg-ink">
              {[
                ["Owner", name.trim()],
                ["Data", "Synced to this account"],
                ["Autonomy", autonomy],
                ["First device", "This browser"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-4 px-4 py-3">
                  <dt className="text-sm text-muted">{k}</dt>
                  <dd className="text-sm capitalize">{v}</dd>
                </div>
              ))}
            </dl>
            <button
              type="button"
              onClick={() =>
                completeSetup(
                  {
                    name: name.trim(),
                    createdAt: new Date().toISOString(),
                    recoveryCodes: codes,
                  },
                  autonomy,
                )
              }
              className="mt-6 h-12 w-full rounded-2xl bg-accent font-medium text-accent-ink"
            >
              Enter Vishnu
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
