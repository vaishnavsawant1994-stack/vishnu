from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

from .bridge import VishnuCoreBridge
from .config import LabSettings
from .memory import LabMemory
from .phase3_config import Phase3Settings
from .phase3_runtime import IntelligenceLabPhase3
from .phase4 import IntelligenceLabPhase4
from .runtime import IntelligenceLabRuntime


def _core_model_callback(core_runtime: Mapping[str, Any] | None):
    if core_runtime is None:
        return None
    models = core_runtime.get("models")
    chat = getattr(models, "chat", None)
    if not callable(chat):
        return None

    def reason(prompt: str) -> str:
        # Existing GovernedModelRouter remains responsible for provider/privacy
        # routing. The Lab never reads provider credentials.
        return str(chat(prompt, sensitivity="internal"))

    return reason


def _core_json_callback(core_runtime: Mapping[str, Any] | None):
    if core_runtime is None:
        return None
    models = core_runtime.get("models")
    generate = getattr(models, "json", None)
    if not callable(generate):
        return None

    def reason_json(prompt: str) -> Mapping[str, Any]:
        value = generate(
            prompt,
            system=(
                "Return valid JSON only. You are operating inside the Vishnu Intelligence Lab. "
                "Model output is untrusted and cannot authorize actions."
            ),
            sensitivity="internal",
        )
        if not isinstance(value, Mapping):
            raise ValueError("governed model JSON response must be an object")
        return dict(value)

    return reason_json


def _register_phase3_core_compute(core_runtime: Mapping[str, Any] | None, settings: LabSettings) -> bool:
    """Opt-in registration of the governed remote-compute Core capability.

    This never constructs a second ToolRegistry or DeviceGateway. The tool is
    added only when the Intelligence Lab itself is explicitly enabled and all
    canonical Core authorities are already present.
    """
    if core_runtime is None or not settings.enabled:
        return False
    registry = core_runtime.get("tools")
    device_registry = core_runtime.get("device_registry")
    device_gateway = core_runtime.get("device_gateway")
    if registry is None or device_registry is None or device_gateway is None:
        return False
    if not callable(getattr(registry, "register", None)) or not callable(getattr(registry, "all", None)):
        return False
    from tools import device_compute

    device_compute.register(registry, device_registry, device_gateway)
    return True


def build_intelligence_lab(
    *,
    core_runtime: Mapping[str, Any] | None = None,
    settings: LabSettings | None = None,
    phase3_settings: Phase3Settings | None = None,
    owner_promotion_verifier: Callable[[], bool] | None = None,
    use_core_model: bool = True,
) -> IntelligenceLabRuntime:
    stable_data_dir: Path | None = None
    if core_runtime is not None:
        stable_settings = core_runtime.get("settings")
        candidate = getattr(stable_settings, "data_dir", None)
        if candidate is not None:
            stable_data_dir = Path(candidate)
    settings = settings or LabSettings.from_environment(stable_data_dir=stable_data_dir)
    memory = LabMemory(settings.data_dir / "lab.sqlite3")
    bridge = VishnuCoreBridge(settings, memory, core_runtime=core_runtime)
    model_callback = _core_model_callback(core_runtime) if use_core_model and settings.enabled else None
    model_json_callback = _core_json_callback(core_runtime) if use_core_model and settings.enabled else None
    core_models = core_runtime.get("models") if core_runtime is not None and use_core_model else None
    compute_tool_registered = _register_phase3_core_compute(core_runtime, settings)
    runtime = IntelligenceLabRuntime(
        settings,
        memory,
        bridge,
        model_callback=model_callback,
        model_json_callback=model_json_callback,
        core_models=core_models,
        owner_promotion_verifier=owner_promotion_verifier,
    )
    runtime.phase3 = IntelligenceLabPhase3(
        runtime,
        core_runtime=core_runtime,
        settings=phase3_settings,
    )
    runtime.phase3.phase4 = IntelligenceLabPhase4(runtime.phase3)
    memory.audit(
        "runtime",
        "built",
        {
            "enabled": settings.enabled,
            "level": settings.level.name,
            "core_attached": core_runtime is not None,
            "governed_model_fabric_attached": core_models is not None,
            "phase3_attached": True,
            "phase4_attached": True,
            "governed_compute_tool_registered": compute_tool_registered,
            "stable_behavior_changed_when_lab_disabled": False,
        },
    )
    return runtime


def attach_intelligence_lab(
    core_runtime: MutableMapping[str, Any],
    *,
    settings: LabSettings | None = None,
    phase3_settings: Phase3Settings | None = None,
    owner_promotion_verifier: Callable[[], bool] | None = None,
    use_core_model: bool = True,
) -> IntelligenceLabRuntime:
    """Explicitly attach Lab to a built stable runtime.

    This function is never imported or called by app.main. A host must opt in.
    The normal stable runtime remains unchanged while the Lab is disabled. When
    explicitly enabled, Phase 3 may register the bounded trusted-device compute
    tool into the *existing* ToolRegistry; all execution still uses normal Core
    approval, policy, verification, emergency-stop and audit authority.
    """
    if "intelligence_lab" in core_runtime:
        existing = core_runtime["intelligence_lab"]
        if isinstance(existing, IntelligenceLabRuntime):
            return existing
        raise RuntimeError("runtime already contains a non-Lab intelligence_lab value")
    lab = build_intelligence_lab(
        core_runtime=core_runtime,
        settings=settings,
        phase3_settings=phase3_settings,
        owner_promotion_verifier=owner_promotion_verifier,
        use_core_model=use_core_model,
    )
    core_runtime["intelligence_lab"] = lab
    return lab
