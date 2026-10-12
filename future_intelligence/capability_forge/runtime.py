from __future__ import annotations

from pathlib import Path

from .event_bridge import attach_capability_forge_observers
from .service import CapabilityForgeService
from .store import CapabilityForgeStore


def build_capability_forge(
    data_dir: str | Path,
    *,
    catalog=None,
    events=None,
    attach_observers: bool = True,
) -> CapabilityForgeService:
    """Construct the F1 Forge service using Vishnu's data directory.

    The returned service is proposal-only. Passing the existing Universal
    Capability catalog enables reuse planning without transferring execution
    authority into Forge.
    """
    root = Path(data_dir)
    service = CapabilityForgeService(
        CapabilityForgeStore(root / "capability-forge.sqlite3"),
        catalog=catalog,
        events=events,
    )
    if events is not None and attach_observers:
        detach = attach_capability_forge_observers(events, service)
        # Runtime owners may call this during controlled shutdown/tests.
        service.detach_event_observers = detach  # type: ignore[attr-defined]
    return service
