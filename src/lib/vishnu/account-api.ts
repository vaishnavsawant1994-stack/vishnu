import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";
import { authMiddleware } from "@/lib/auth/middleware";

type StoredPasskeyOptions = {
  challenge: string;
  rpId?: string;
  timeout?: number;
  userVerification?: string;
  attestation?: string;
  rp?: { id?: string; name: string };
  user?: { id: string; name: string; displayName: string };
  pubKeyCredParams?: { alg: number; type: "public-key" }[];
  authenticatorSelection?: {
    authenticatorAttachment?: "platform" | "cross-platform";
    residentKey?: "discouraged" | "preferred" | "required";
    requireResidentKey?: boolean;
    userVerification?: "discouraged" | "preferred" | "required";
  };
  excludeCredentials?: { id: string; type: "public-key" }[];
  allowCredentials?: { id: string; type: "public-key" }[];
};

function storedOptions(options: object): StoredPasskeyOptions {
  const copy = { ...options } as { extensions?: unknown };
  delete copy.extensions;
  return JSON.parse(JSON.stringify(copy)) as StoredPasskeyOptions;
}

type SessionResult = { ok: true; token: string } | { ok: false; message: string };

function originInfo() {
  const req = getRequest();
  const forwardedHost = req.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const host = forwardedHost || req.headers.get("host") || "localhost";
  const hostname = host.split(":")[0] || "localhost";
  const forwardedProto = req.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  const proto =
    forwardedProto || (hostname === "localhost" || hostname === "127.0.0.1" ? "http" : "https");
  return { rpID: hostname, origin: `${proto}://${host}` };
}

function code() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = randomBytes(8);
  let text = "";
  for (const byte of bytes) text += alphabet[byte % alphabet.length];
  return `VISHNU-${text.slice(0, 4)}-${text.slice(4)}`;
}

function hashCode(value: string) {
  return createHash("sha256").update(value.trim().toLowerCase()).digest();
}

function hashesMatch(stored: string, next: Buffer) {
  const left = Buffer.from(stored, "hex");
  if (left.length !== next.length) return false;
  return timingSafeEqual(left, next);
}

async function authContext() {
  const { auth } = await import("@/lib/auth/server");
  return auth.$context;
}

async function openSession(userId: string): Promise<string> {
  const ctx = await authContext();
  const session = await ctx.internalAdapter.createSession(userId);
  if (!session?.token) throw new Error("Could not open a session");
  return session.token;
}

async function setPassword(userId: string, password: string) {
  const ctx = await authContext();
  const hashed = await ctx.password.hash(password);
  const accounts = await ctx.internalAdapter.findAccounts(userId);
  const credential = accounts.find((account) => account.providerId === "credential");
  if (!credential) {
    await ctx.internalAdapter.createAccount({
      userId,
      providerId: "credential",
      accountId: userId,
      password: hashed,
    });
  } else {
    await ctx.internalAdapter.updatePassword(userId, hashed);
  }
}

export const issueRecoveryCodes = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }): Promise<{ email: string | null; codes: string[] }> => {
    const { getSql } = await import("@/lib/db");
    const sql = await getSql();
    const users = await sql<{ email: string }>`
      select email from "user" where id = ${context.userId}
    `;
    const email = users[0]?.email ?? null;
    if (!email) return { email: null, codes: [] };
    const codes = Array.from({ length: 8 }, () => code());
    const hashes = JSON.stringify(codes.map((item) => hashCode(item).toString("hex")));
    await sql`
      insert into vishnu_recovery (user_id, email, code_hashes, updated_at)
      values (${context.userId}, ${email}, ${hashes}, now())
      on conflict (user_id) do update
        set email = excluded.email, code_hashes = excluded.code_hashes, updated_at = now()
    `;
    return { email, codes };
  });

export const resetWithRecovery = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Missing reset");
    const row = input as { email?: unknown; code?: unknown; password?: unknown };
    const email = typeof row.email === "string" ? row.email.trim().toLowerCase() : "";
    const codeValue = typeof row.code === "string" ? row.code.trim() : "";
    const password = typeof row.password === "string" ? row.password : "";
    if (!email.includes("@") || codeValue.length < 8 || password.length < 8) {
      throw new Error("Email, recovery code, and a password of at least 8 characters are required");
    }
    return { email, code: codeValue, password };
  })
  .handler(async ({ data }): Promise<SessionResult> => {
    const { assertSameSiteRequest } = await import("@/lib/auth/isolation.server");
    assertSameSiteRequest();
    const { getSql } = await import("@/lib/db");
    const sql = await getSql();
    const rows = await sql<{ user_id: string; code_hashes: string }>`
      select user_id, code_hashes from vishnu_recovery where lower(email) = ${data.email}
    `;
    const row = rows[0];
    if (!row) return { ok: false, message: "No recovery codes match that email." };
    const hashes = JSON.parse(row.code_hashes) as unknown;
    if (!Array.isArray(hashes)) return { ok: false, message: "Recovery codes are unreadable." };
    const next = hashCode(data.code);
    const hit = hashes.findIndex((item) => typeof item === "string" && hashesMatch(item, next));
    if (hit < 0) return { ok: false, message: "That recovery code does not match." };
    hashes.splice(hit, 1);
    await sql`
      update vishnu_recovery set code_hashes = ${JSON.stringify(hashes)}, updated_at = now()
      where user_id = ${row.user_id}
    `;
    await setPassword(row.user_id, data.password);
    return { ok: true, token: await openSession(row.user_id) };
  });

export const passkeyRegisterOptions = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }) => {
    const { getSql } = await import("@/lib/db");
    const { generateRegistrationOptions } = await import("@simplewebauthn/server");
    const sql = await getSql();
    const users = await sql<{ email: string; name: string }>`
      select email, name from "user" where id = ${context.userId}
    `;
    const existing = await sql<{ credential_id: string }>`
      select credential_id from vishnu_passkeys where user_id = ${context.userId}
    `;
    const { rpID, origin } = originInfo();
    const userName = users[0]?.email || context.userId;
    const options = await generateRegistrationOptions({
      rpName: "Vishnu",
      rpID,
      userName,
      userID: new TextEncoder().encode(context.userId),
      userDisplayName: users[0]?.name || "Vishnu owner",
      attestationType: "none",
      authenticatorSelection: {
        residentKey: "required",
        userVerification: "preferred",
      },
      excludeCredentials: existing.map((row) => ({ id: row.credential_id })),
    });
    const id = randomBytes(16).toString("hex");
    const expires = new Date(Date.now() + 5 * 60 * 1000).toISOString();
    await sql`
      insert into vishnu_challenges (id, user_id, challenge, kind, expires_at)
      values (${id}, ${context.userId}, ${options.challenge}, 'register', ${expires})
    `;
    return { options: storedOptions(options), challengeId: id, origin };
  });

export const passkeyRegisterVerify = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Missing passkey");
    const row = input as { challengeId?: unknown; response?: unknown };
    if (typeof row.challengeId !== "string" || !row.response || typeof row.response !== "object") {
      throw new Error("Bad passkey");
    }
    return { challengeId: row.challengeId, response: row.response };
  })
  .handler(async ({ context, data }) => {
    const { getSql } = await import("@/lib/db");
    const { verifyRegistrationResponse } = await import("@simplewebauthn/server");
    const sql = await getSql();
    const rows = await sql<{ challenge: string }>`
      delete from vishnu_challenges
      where id = ${data.challengeId} and user_id = ${context.userId} and kind = 'register' and expires_at > now()
      returning challenge
    `;
    const challenge = rows[0]?.challenge;
    if (!challenge) return { ok: false as const, message: "That passkey prompt expired. Try again." };
    const { rpID, origin } = originInfo();
    const verified = await verifyRegistrationResponse({
      response: data.response as never,
      expectedChallenge: challenge,
      expectedOrigin: origin,
      expectedRPID: rpID,
      requireUserVerification: false,
    });
    if (!verified.verified) return { ok: false as const, message: "This browser did not accept the passkey." };
    const credential = verified.registrationInfo.credential;
    await sql`
      insert into vishnu_passkeys (credential_id, user_id, public_key, counter)
      values (
        ${credential.id},
        ${context.userId},
        ${Buffer.from(credential.publicKey).toString("base64url")},
        ${credential.counter}
      )
      on conflict (credential_id) do nothing
    `;
    return { ok: true as const, message: "Passkey saved for this account." };
  });

export const passkeySignInOptions = createServerFn({ method: "POST" })
  .validator(() => ({}))
  .handler(async () => {
    const { assertSameSiteRequest } = await import("@/lib/auth/isolation.server");
    assertSameSiteRequest();
    const { getSql } = await import("@/lib/db");
    const { generateAuthenticationOptions } = await import("@simplewebauthn/server");
    const { rpID } = originInfo();
    const options = await generateAuthenticationOptions({
      rpID,
      userVerification: "preferred",
    });
    const sql = await getSql();
    const id = randomBytes(16).toString("hex");
    const expires = new Date(Date.now() + 5 * 60 * 1000).toISOString();
    await sql`
      insert into vishnu_challenges (id, user_id, challenge, kind, expires_at)
      values (${id}, null, ${options.challenge}, 'sign-in', ${expires})
    `;
    return { options: storedOptions(options), challengeId: id };
  });

export const passkeySignInVerify = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Missing passkey");
    const row = input as { challengeId?: unknown; response?: unknown };
    if (typeof row.challengeId !== "string" || !row.response || typeof row.response !== "object") {
      throw new Error("Bad passkey");
    }
    const response = row.response as { id?: unknown };
    if (typeof response.id !== "string") throw new Error("Bad passkey");
    return { challengeId: row.challengeId, response: row.response, credentialId: response.id };
  })
  .handler(async ({ data }): Promise<SessionResult> => {
    const { assertSameSiteRequest } = await import("@/lib/auth/isolation.server");
    assertSameSiteRequest();
    const { getSql } = await import("@/lib/db");
    const { verifyAuthenticationResponse } = await import("@simplewebauthn/server");
    const sql = await getSql();
    const challenges = await sql<{ challenge: string }>`
      delete from vishnu_challenges
      where id = ${data.challengeId} and kind = 'sign-in' and expires_at > now()
      returning challenge
    `;
    const challenge = challenges[0]?.challenge;
    if (!challenge) return { ok: false, message: "That passkey prompt expired. Try again." };
    const keys = await sql<{ user_id: string; public_key: string; counter: string }>`
      select user_id, public_key, counter from vishnu_passkeys where credential_id = ${data.credentialId}
    `;
    const key = keys[0];
    if (!key) return { ok: false, message: "This passkey is not registered on Vishnu." };
    const { rpID, origin } = originInfo();
    const verified = await verifyAuthenticationResponse({
      response: data.response as never,
      expectedChallenge: challenge,
      expectedOrigin: origin,
      expectedRPID: rpID,
      requireUserVerification: false,
      credential: {
        id: data.credentialId,
        publicKey: new Uint8Array(Buffer.from(key.public_key, "base64url")),
        counter: Number(key.counter),
      },
    });
    if (!verified.verified) return { ok: false, message: "Passkey check failed." };
    await sql`
      update vishnu_passkeys set counter = ${verified.authenticationInfo.newCounter}
      where credential_id = ${data.credentialId}
    `;
    return { ok: true, token: await openSession(key.user_id) };
  });

type DeviceRow = {
  id: string;
  name?: string;
  code?: string;
  revoked?: boolean;
  connected?: boolean;
  lastSeen?: string;
};

export const connectPairedDevice = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Missing code");
    const code = (input as { code?: unknown }).code;
    if (typeof code !== "string" || code.trim().length < 8) throw new Error("Missing code");
    return { code: code.trim() };
  })
  .handler(async ({ context, data }) => {
    const { getSql } = await import("@/lib/db");
    const sql = await getSql();
    const rows = await sql<{ doc: string }>`
      select doc from vishnu_workspaces where user_id = ${context.userId}
    `;
    const raw = rows[0]?.doc;
    if (!raw) return { ok: false as const, message: "This account has no workspace yet. Finish setup on the first screen.", doc: null };
    const doc = JSON.parse(raw) as { devices?: DeviceRow[] };
    const devices = Array.isArray(doc.devices) ? doc.devices : [];
    const hit = devices.find((device) => device.code?.toLowerCase() === data.code.toLowerCase() && !device.revoked);
    if (!hit) return { ok: false as const, message: "No device is waiting for that code on this account.", doc: raw };
    hit.connected = true;
    hit.lastSeen = new Date().toISOString();
    const next = JSON.stringify({ ...doc, devices });
    await sql`
      update vishnu_workspaces set doc = ${next}, updated_at = now() where user_id = ${context.userId}
    `;
    return { ok: true as const, message: `Connected ${"name" in hit && typeof (hit as { name?: string }).name === "string" ? (hit as { name: string }).name : "device"}.`, doc: next };
  });
