export type Secret = { id: string; name: string; value: string };

const ITERATIONS = 600_000;

function encode(bytes: Uint8Array) {
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text);
}

function decode(value: string) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function copyBytes(value: Uint8Array) {
  const out = new Uint8Array(new ArrayBuffer(value.byteLength));
  out.set(value);
  return out;
}

async function derive(passphrase: string, salt: Uint8Array) {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: copyBytes(salt), iterations: ITERATIONS, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function sealVault(passphrase: string, secrets: Secret[]) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await derive(passphrase, salt);
  const cipher = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: copyBytes(iv) },
    key,
    new TextEncoder().encode(JSON.stringify(secrets)),
  );
  return {
    salt: encode(salt),
    iv: encode(iv),
    ciphertext: encode(new Uint8Array(cipher)),
    updatedAt: new Date().toISOString(),
  };
}

export async function openVault(
  passphrase: string,
  vault: { salt: string; iv: string; ciphertext: string },
): Promise<Secret[]> {
  const key = await derive(passphrase, decode(vault.salt));
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: copyBytes(decode(vault.iv)) },
    key,
    decode(vault.ciphertext),
  );
  const data = JSON.parse(new TextDecoder().decode(plain)) as unknown;
  if (!Array.isArray(data)) throw new Error("Vault payload is not a secret list");
  return data.filter((item): item is Secret => {
    if (!item || typeof item !== "object") return false;
    const row = item as Secret;
    return typeof row.id === "string" && typeof row.name === "string" && typeof row.value === "string";
  });
}
