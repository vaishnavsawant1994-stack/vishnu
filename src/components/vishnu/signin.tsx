import { useState, type FormEvent } from "react";
import { useRouter } from "@tanstack/react-router";
import { toast } from "sonner";
import { authClient, GROK_PROVIDERS, signIn } from "@/lib/auth/client";
import { RecoveryReset, signInWithPasskey, usePasskeyAvailable } from "./account";
import { NeuralCore } from "./core";

export function SignInPanel() {
  const router = useRouter();
  const passkey = usePasskeyAvailable();
  const [mode, setMode] = useState<"in" | "up" | "reset">("in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result =
        mode === "up"
          ? await authClient.signUp.email({ email, password, name: name || email })
          : await authClient.signIn.email({ email, password });
      if (result.error) {
        toast(result.error.message || "Sign-in failed");
        return;
      }
      await router.invalidate();
    } catch (error) {
      toast(error instanceof Error ? error.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-frame flex items-center justify-center overflow-auto bg-bg px-4 py-8">
      <section className="w-full max-w-md">
        <NeuralCore size="sm" />
        <h1 className="text-center text-2xl font-medium">Sign in to Vishnu</h1>
        <p className="mt-2 text-center text-sm text-muted">
          Google, X, email, or a passkey you already created. The workspace follows that account.
        </p>
        {mode !== "reset" && (
          <div className="mt-6 grid gap-2">
            {GROK_PROVIDERS.map((provider) => (
              <button
                key={provider.providerId}
                type="button"
                onClick={() => signIn(provider.providerId, { callbackURL: "/" })}
                className="h-12 rounded-2xl border border-line bg-ink text-sm"
              >
                Continue with {provider.label}
              </button>
            ))}
            {passkey && (
              <button
                type="button"
                className="h-12 rounded-2xl border border-line bg-ink text-sm"
                onClick={() => {
                  void signInWithPasskey().catch((error: unknown) => {
                    toast(
                      error instanceof Error && /invalid domain/i.test(error.message)
                        ? "Passkeys need this site’s name. A numeric address cannot store one."
                        : error instanceof Error
                          ? error.message
                          : "Passkey sign-in failed",
                    );
                  });
                }}
              >
                Use a passkey
              </button>
            )}
          </div>
        )}
        {mode === "reset" ? (
          <div className="mt-6 border-t border-line pt-6">
            <RecoveryReset onDone={() => setMode("in")} />
            <button type="button" onClick={() => setMode("in")} className="mt-2 h-11 text-sm text-muted">
              Back to sign in
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-6 grid gap-2 border-t border-line pt-6">
            {mode === "up" && (
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name"
                aria-label="Name"
                className="h-12 rounded-2xl border border-line bg-ink px-4 text-base"
              />
            )}
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              aria-label="Email"
              className="h-12 rounded-2xl border border-line bg-ink px-4 text-base"
            />
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              aria-label="Password"
              className="h-12 rounded-2xl border border-line bg-ink px-4 text-base"
            />
            <button type="submit" disabled={busy} className="h-12 rounded-2xl bg-accent font-medium text-accent-ink disabled:opacity-40">
              {mode === "up" ? "Create account" : "Sign in with email"}
            </button>
            <button type="button" onClick={() => setMode(mode === "in" ? "up" : "in")} className="h-11 text-sm text-muted">
              {mode === "in" ? "Need an account? Create one" : "Already have an account? Sign in"}
            </button>
            {mode === "in" && (
              <button type="button" onClick={() => setMode("reset")} className="h-11 text-sm text-muted">
                Forgot the password? Use a recovery code
              </button>
            )}
          </form>
        )}
      </section>
    </main>
  );
}
