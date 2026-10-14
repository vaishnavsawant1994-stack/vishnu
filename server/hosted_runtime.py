from __future__ import annotations

import os
import threading

from app.e9_runtime import start_e9_services
from app.main import _close_runtime, build_runtime
from core.config import settings
from onboarding.first_run import FirstRunCoordinator
from server.agent_continuity_api import agent_continuity_router
from server.api import create_app
from server.evidence_api import evidence_router
from server.evolution_api import evolution_router
from server.identity_api import identity_router
from server.model_provider_api import model_provider_router
from server.sensorium_physical_api import sensorium_physical_router


def create_hosted_app():
    """Build Vishnu without a desktop GUI for an owner-selected HTTPS host.

    The hosted process uses the same canonical runtime, first-run coordinator,
    owner authority, device registry, recovery service, and API composition as
    the desktop application. Background work is deliberately held until the
    owner finishes first-run setup.
    """

    FirstRunCoordinator.apply_pending_restore(
        settings.data_dir,
        vault_password=settings.vault_password or None,
    )
    runtime = build_runtime()
    setup = FirstRunCoordinator(settings.data_dir, runtime=runtime)
    runtime["first_run_setup"] = setup
    runtime["setup_surface"] = "hosted"

    composition = runtime["composition"]
    app = create_app(
        composition.work.turn_runtime,
        settings,
        device_registry=composition.devices.registry,
        device_gateway=composition.devices.gateway,
        second_brain=composition.memory.second_brain,
        automations=composition.work.automation_engine,
        runtime=runtime,
    )
    app.include_router(evolution_router(runtime))
    app.include_router(identity_router(runtime))
    app.include_router(evidence_router(runtime))
    app.include_router(agent_continuity_router(runtime))
    app.include_router(model_provider_router(runtime))
    app.include_router(sensorium_physical_router(runtime), prefix="/owner/ai")

    stop_event = threading.Event()
    services_started = threading.Event()

    def start_when_ready() -> None:
        while not stop_event.wait(0.5):
            if not setup.ready:
                continue
            composition.work.automation_engine.start()
            start_e9_services(runtime)
            services_started.set()
            return

    def on_startup() -> None:
        threading.Thread(
            target=start_when_ready,
            name="vishnu-hosted-first-run-gate",
            daemon=True,
        ).start()

    def on_shutdown() -> None:
        stop_event.set()
        _close_runtime(runtime, services_started=services_started.is_set())

    app.add_event_handler("startup", on_startup)
    app.add_event_handler("shutdown", on_shutdown)

    @app.get("/hosted-health", include_in_schema=False)
    def hosted_health() -> dict[str, object]:
        return {
            "ok": True,
            "initialized": bool(setup.ready),
            "surface": "hosted",
        }

    app.state.vishnu_runtime = runtime
    return app


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    # A hosted runtime is reached through the provider's TLS ingress. Trust
    # forwarded scheme headers only when the deployment template explicitly
    # opts into that proxy boundary.
    trust_proxy = os.environ.get("PERSONAL_AI_TRUST_PROXY_HEADERS", "").strip().lower()
    forwarded_allow_ips = "*" if trust_proxy in {"1", "true", "yes", "on"} else "127.0.0.1"
    uvicorn.run(
        create_hosted_app(),
        host="0.0.0.0",
        port=port,
        log_level="warning",
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
