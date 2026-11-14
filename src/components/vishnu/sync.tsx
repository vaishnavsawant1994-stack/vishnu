import { useEffect } from "react";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import { loadWorkspace, saveWorkspace } from "@/lib/vishnu/sync-api";
import { useVishnu, workspaceSnapshot, type VishnuData } from "@/lib/vishnu/store";

export function WorkspaceSync() {
  const { user } = useCurrentUserState();
  const userId = user?.id ?? null;

  useEffect(() => {
    if (!userId) return;
    let stopped = false;
    let ready = false;
    let last = "";
    let timer = 0;

    void (async () => {
      useVishnu.getState().setSyncState("loading");
      try {
        const remote = await loadWorkspace();
        if (stopped) return;
        const raw = remote && typeof remote === "object" && "doc" in remote ? remote.doc : null;
        if (typeof raw === "string" && raw) {
          try {
            const doc = JSON.parse(raw) as unknown;
            if (doc && typeof doc === "object") useVishnu.getState().hydrateFromServer(doc as Partial<VishnuData>);
          } catch {
            /* ignore a damaged remote copy and keep local */
          }
        } else if (useVishnu.getState().owner) {
          await saveWorkspace({ data: { doc: workspaceSnapshot(useVishnu.getState()) } });
        }
        if (!stopped) useVishnu.getState().setSyncState("ready");
      } catch {
        if (!stopped) useVishnu.getState().setSyncState("offline");
      }
      if (stopped) return;
      last = JSON.stringify(workspaceSnapshot(useVishnu.getState()));
      ready = true;
    })();

    const unsub = useVishnu.subscribe((state) => {
      if (!ready || state.settings.storageSync === false) return;
      const raw = JSON.stringify(workspaceSnapshot(state));
      if (raw === last) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        last = raw;
        void saveWorkspace({ data: { doc: JSON.parse(raw) as Record<string, unknown> } }).catch(() => {
          last = "";
        });
      }, 800);
    });

    return () => {
      stopped = true;
      ready = false;
      unsub();
      window.clearTimeout(timer);
    };
  }, [userId]);

  return null;
}
