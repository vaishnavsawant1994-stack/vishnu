"""Owner/device-scoped P2-08 command history. No execution authority here."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from security.request_context import current_trusted_request

# Stable identifiers for owner navigation/creation entries. This is an
# allow-list for history metadata, NOT an executable tool registry.
KNOWN = frozenset("""
home chat today workspaces projects agents library tools devices settings search notifications
new-chat new-project new-workspace new-task new-automation new-note upload-file
summarize-day summarize-this analyze-file extract-actions research-agent custom-agent
schedule-meeting draft-email recent-work needs-approval
""".split())
KEY = "command_center.history.v2"


class RecentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=50)
    # No query, source content, private filenames, args, credentials or prompts.


def command_center_router(runtime: dict) -> APIRouter:
    router = APIRouter(prefix="/iphone/api/command-center", tags=["command-center"])
    registry = runtime["device_registry"]

    def owner(device: str | None, token: str | None):
        if not device or not token or not registry.authenticate(device, token):
            raise HTTPException(401, "Trusted device/session required")
        if hasattr(registry, "authorize") and not registry.authorize(device, "ai:chat"):
            raise HTTPException(403, "Device is not permitted to inspect commands")
        return device

    def authorize_write(device):
        context = current_trusted_request()
        if context is None or context.device_id != device or not registry.is_active(device):
            raise HTTPException(401, 'Current matching trusted owner session required')

    def load(device):
        try:
            raw = registry.metadata(device).get(KEY, "[]")
            records = json.loads(raw)
            if not isinstance(records, list):
                return []
            return [
                {"id": x["id"], "at": x["at"]}
                for x in records[:12]
                if isinstance(x, dict) and x.get("id") in KNOWN
                and isinstance(x.get("at"), str) and len(x["at"]) < 48
            ]
        except (ValueError, TypeError, AttributeError, KeyError):
            return []

    def save(device, entries):
        value = json.dumps(entries[:12], separators=(",", ":"), sort_keys=True)
        if not registry.set_metadata(device, KEY, value):
            raise HTTPException(404, "Trusted device not found")

    @router.get("/recent")
    def recent(pa_device: str | None = Cookie(default=None),
               pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        return {"recent": load(device), "scope": "trusted_device", "storage": "device_registry"}

    @router.post("/recent")
    def record(body: RecentEntry, pa_device: str | None = Cookie(default=None),
               pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        authorize_write(device)
        if body.command_id not in KNOWN:
            raise HTTPException(422, "Unknown command identifier")
        # History has no execution power and cannot affirm an action outcome.
        entries = [{"id": body.command_id,
                    "at": datetime.now(timezone.utc).isoformat()}]
        entries.extend(x for x in load(device) if x["id"] != body.command_id)
        save(device, entries)
        return {"recent": entries[:12]}

    @router.delete("/recent")
    def clear(pa_device: str | None = Cookie(default=None),
              pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        authorize_write(device)
        save(device, [])
        return {"cleared": True}

    return router
