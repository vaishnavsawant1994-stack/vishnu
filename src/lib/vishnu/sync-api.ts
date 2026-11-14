import { createServerFn } from "@tanstack/react-start";
import { authMiddleware } from "@/lib/auth/middleware";
import { getSql } from "@/lib/db";

const MAX = 1_500_000;

type DeviceShape = { id?: string; connected?: boolean; revoked?: boolean; lastSeen?: string };

function mergeDevices(previousRaw: string, nextRaw: string) {
  try {
    const previous = JSON.parse(previousRaw) as { devices?: DeviceShape[] };
    const next = JSON.parse(nextRaw) as { devices?: DeviceShape[] };
    const prior = new Map((previous.devices ?? []).map((device) => [device.id, device]));
    next.devices = (next.devices ?? []).map((device) => {
      const older = device.id ? prior.get(device.id) : undefined;
      if (older?.connected && !device.connected && !device.revoked) {
        return { ...device, connected: true, lastSeen: older.lastSeen ?? device.lastSeen };
      }
      return device;
    });
    return JSON.stringify(next);
  } catch {
    return nextRaw;
  }
}

export const loadWorkspace = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }) => {
    const sql = await getSql();
    const rows = await sql<{ doc: string }>`
      select doc from vishnu_workspaces where user_id = ${context.userId}
    `;
    const raw = rows[0]?.doc;
    if (!raw) return { doc: null as string | null };
    return { doc: raw };
  });

export const saveWorkspace = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((input: unknown) => {
    if (!input || typeof input !== "object" || !("doc" in input)) throw new Error("Missing workspace");
    const doc = (input as { doc: unknown }).doc;
    if (!doc || typeof doc !== "object") throw new Error("Bad workspace");
    const raw = JSON.stringify(doc);
    if (raw.length > MAX) throw new Error("Workspace is too large to sync");
    return { raw };
  })
  .handler(async ({ context, data }) => {
    const sql = await getSql();
    const rows = await sql<{ doc: string }>`
      select doc from vishnu_workspaces where user_id = ${context.userId}
    `;
    const raw = rows[0]?.doc ? mergeDevices(rows[0].doc, data.raw) : data.raw;
    if (raw.length > MAX) throw new Error("Workspace is too large to sync");
    await sql`
      insert into vishnu_workspaces (user_id, doc, updated_at)
      values (${context.userId}, ${raw}, now())
      on conflict (user_id) do update set doc = excluded.doc, updated_at = now()
    `;
    return { ok: true as const };
  });
