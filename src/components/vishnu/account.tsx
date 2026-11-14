import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useRefetchWhenConnectorReady } from "@/lib/app-data";
import { redirectToLoginIfRequired } from "@/lib/app-data/login";
import {
  issueRecoveryCodes,
  passkeyRegisterOptions,
  passkeyRegisterVerify,
  passkeySignInOptions,
  passkeySignInVerify,
  resetWithRecovery,
} from "@/lib/vishnu/account-api";
import { readConnectors, type OutsideResult } from "@/lib/vishnu/outside-api";
import { rememberSession } from "@/lib/vishnu/session-client";
import { useVishnu } from "@/lib/vishnu/store";

function passkeyError(error: unknown, fallback: string) {
  const message = error instanceof Error ? error.message : fallback;
  if (/invalid domain/i.test(message)) {
    return "Passkeys need this site’s name. A numeric address cannot store one. Use email or a recovery code here.";
  }
  return message;
}

export function rememberAndEnter(token: string) {
  rememberSession(token);
}

async function enterWithToken(token: string) {
  rememberSession(token);
  window.location.assign("/");
}

export function usePasskeyAvailable() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(typeof window !== "undefined" && "PublicKeyCredential" in window);
  }, []);
  return ready;
}

export async function signInWithPasskey() {
  const { startAuthentication } = await import("@simplewebauthn/browser");
  const started = await passkeySignInOptions({ data: {} });
  const response = await startAuthentication({
    optionsJSON: started.options as Parameters<typeof startAuthentication>[0]["optionsJSON"],
  });
  const result = await passkeySignInVerify({ data: { challengeId: started.challengeId, response } });
  if (!result.ok) throw new Error(result.message);
  await enterWithToken(result.token);
}

export function RecoveryReset({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="grid gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        void resetWithRecovery({ data: { email, code, password } })
          .then(async (result) => {
            if (!result.ok) {
              toast(result.message);
              return;
            }
            await enterWithToken(result.token);
            onDone();
          })
          .catch((error: unknown) => toast(error instanceof Error ? error.message : "Reset failed"))
          .finally(() => setBusy(false));
      }}
    >
      <input
        type="email"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder="Email"
        aria-label="Email"
        className="h-12 rounded-2xl border border-line bg-ink px-4 text-base"
      />
      <input
        value={code}
        onChange={(event) => setCode(event.target.value)}
        placeholder="Recovery code"
        aria-label="Recovery code"
        className="h-12 rounded-2xl border border-line bg-ink px-4 text-base"
      />
      <input
        type="password"
        required
        minLength={8}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        placeholder="New password"
        aria-label="New password"
        className="h-12 rounded-2xl border border-line bg-ink px-4 text-base"
      />
      <button type="submit" disabled={busy} className="h-12 rounded-2xl bg-accent font-medium text-accent-ink disabled:opacity-40">
        Set password and sign in
      </button>
    </form>
  );
}

export function AccountAccess() {
  const passkey = usePasskeyAvailable();
  const [codes, setCodes] = useState<string[]>([]);
  const [email, setEmail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <section className="mt-3 rounded-2xl border border-line bg-ink p-4">
      <h2 className="font-medium">This account on another computer</h2>
      <p className="mt-1 text-sm leading-relaxed text-muted">
        A passkey lets this site recognize you on a phone or another laptop. Recovery codes set a new email password if you forget it. Google and X still work on their own. Passkeys belong to this site address, not to every website.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {passkey && (
          <button
            type="button"
            disabled={busy}
            className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink disabled:opacity-40"
            onClick={() => {
              setBusy(true);
              void (async () => {
                try {
                  const { startRegistration } = await import("@simplewebauthn/browser");
                  const started = await passkeyRegisterOptions();
                  const response = await startRegistration({
                    optionsJSON: started.options as Parameters<typeof startRegistration>[0]["optionsJSON"],
                  });
                  const result = await passkeyRegisterVerify({ data: { challengeId: started.challengeId, response } });
                  toast(result.message);
                } catch (error) {
                  toast(passkeyError(error, "Passkey was not saved"));
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            Create a passkey
          </button>
        )}
        <button
          type="button"
          disabled={busy}
          className="h-11 rounded-xl border border-line px-4 text-sm"
          onClick={() => {
            setBusy(true);
            void issueRecoveryCodes()
              .then((result) => {
                setEmail(result.email);
                setCodes(result.codes);
                if (!result.email) toast("This sign-in has no email, so use a passkey or Google or X.");
                else toast("New recovery codes replace the old ones. Copy them now.");
              })
              .catch((error: unknown) => toast(error instanceof Error ? error.message : "Could not create codes"))
              .finally(() => setBusy(false));
          }}
        >
          Create recovery codes
        </button>
      </div>
      {email && codes.length > 0 && (
        <ul className="mt-3 grid gap-1 sm:grid-cols-2">
          {codes.map((item) => (
            <li key={item} className="font-mono text-sm text-accent">
              {item}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function InstallActions() {
  const [prompt, setPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      ("standalone" in navigator && Boolean((navigator as { standalone?: boolean }).standalone));
    setInstalled(standalone);
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPrompt(event as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  return (
    <section className="mt-4 rounded-2xl border border-line bg-ink p-4">
      <h2 className="font-medium">Install Vishnu</h2>
      <p className="mt-1 text-sm leading-relaxed text-muted">
        {installed
          ? "This screen is already installed."
          : "Windows and Android can install it from the browser. iPhone uses the share sheet. It is the same account, not a separate store app."}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="h-11 rounded-xl bg-accent px-4 text-sm font-medium text-accent-ink disabled:opacity-40"
          disabled={!prompt}
          onClick={() => {
            if (!prompt) {
              toast("This browser has no install prompt yet. Use the menu, or the iPhone steps.");
              return;
            }
            void prompt.prompt();
          }}
        >
          Install on this computer or Android
        </button>
        <a href="/?install=1&platform=ios" className="grid h-11 place-items-center rounded-xl border border-line px-4 text-sm">
          iPhone install steps
        </a>
      </div>
    </section>
  );
}

type BeforeInstallPromptEvent = Event & { prompt: () => Promise<void> };

export function PairingCode({ code }: { code: string }) {
  const [svg, setSvg] = useState("");
  const url = typeof window === "undefined" ? "" : `${window.location.origin}/?pair=${encodeURIComponent(code)}&surface=phone`;

  useEffect(() => {
    let stopped = false;
    void import("qrcode").then(async (mod) => {
      const qr = mod as unknown as {
        toString: (
          text: string,
          opts: { type: "svg"; margin: number; color: { dark: string; light: string } },
        ) => Promise<string>;
      };
      const image = await qr.toString(url, {
        type: "svg",
        margin: 1,
        color: { dark: "#eef3fb", light: "#101826" },
      });
      if (!stopped) setSvg(image);
    });
    return () => {
      stopped = true;
    };
  }, [url]);

  return (
    <div className="mt-3">
      <p className="text-xs text-muted">Scan with the phone camera. It opens Vishnu, signs into this account, and connects this code.</p>
      {svg ? (
        <div className="mt-2 h-36 w-36 [&_svg]:h-full [&_svg]:w-full" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : null}
      <p className="mt-2 break-all font-mono text-xs text-accent">{url}</p>
    </div>
  );
}

export function useOutsideRead() {
  const addTask = useVishnu((s) => s.addTask);
  const addInbox = useVishnu((s) => s.addInbox);
  const log = useVishnu((s) => s.log);
  const [waiting, setWaiting] = useState(false);
  const pendingKind = useRef<"calendar" | "mail" | "files" | null>(null);

  const read = async (kind: "calendar" | "mail" | "files") => {
    let result: OutsideResult;
    try {
      result = await readConnectors({ data: { kind } });
    } catch (error) {
      toast(error instanceof Error ? error.message : "Could not reach the connector");
      return;
    }
    if (result.loginUrl) redirectToLoginIfRequired({ ok: false, data: null, loginRequired: true, loginUrl: result.loginUrl });
    if (result.pending) {
      pendingKind.current = kind;
      setWaiting(true);
      toast(result.message);
      return;
    }
    pendingKind.current = null;
    setWaiting(false);
    if (!result.ok) {
      toast(result.message);
      return;
    }
    if (kind === "calendar") {
      result.items.forEach((item) => addTask(item.title, item.detail || undefined));
    } else {
      result.items.forEach((item) => addInbox(item.title, item.detail || kind));
    }
    log(kind, result.message);
    toast(result.message);
  };

  useRefetchWhenConnectorReady(waiting, () => {
    const kind = pendingKind.current;
    if (kind) return read(kind);
  });

  return read;
}
