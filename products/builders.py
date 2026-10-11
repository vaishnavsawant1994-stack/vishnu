from __future__ import annotations

from dataclasses import dataclass

from .models import PLATFORM_TARGETS, ensure_choice
from .runtime import ProductRuntimeSpec


@dataclass(frozen=True)
class TargetBuilder:
    target: str
    artifact_kinds: tuple[str, ...]
    signing_required: bool
    adapter: str


_BUILDERS = {
    "web": TargetBuilder("web", ("web_bundle",), False, "web"),
    "pwa": TargetBuilder("pwa", ("pwa_bundle",), False, "web"),
    "android": TargetBuilder("android", ("apk", "aab"), True, "android"),
    "ios": TargetBuilder("ios", ("xcarchive",), True, "ios"),
    "windows": TargetBuilder("windows", ("exe", "msi"), True, "windows"),
    "macos": TargetBuilder("macos", ("app", "dmg", "pkg"), True, "macos"),
    "linux": TargetBuilder("linux", ("appimage", "deb", "rpm"), False, "linux"),
    "docker": TargetBuilder("docker", ("oci_image",), True, "docker"),
    "api": TargetBuilder("api", ("api_bundle", "oci_image"), True, "server"),
    "worker": TargetBuilder("worker", ("worker_bundle", "oci_image"), True, "server"),
}


def builder_for(target: str) -> TargetBuilder:
    key = ensure_choice(target, PLATFORM_TARGETS, "platform target")
    return _BUILDERS[key]


def build_plan(spec: ProductRuntimeSpec, target: str) -> dict:
    builder = builder_for(target)
    if target not in spec.targets:
        raise ValueError(f"Target {target} is not enabled for product {spec.product_id}")
    return {
        "product_id": spec.product_id,
        "version": spec.version,
        "target": builder.target,
        "adapter": builder.adapter,
        "artifact_kinds": list(builder.artifact_kinds),
        "signing_required": builder.signing_required,
        "ai_mode": spec.ai_mode,
        "components": [
            {
                "id": item["id"],
                "component_type": item["component_type"],
                "component_ref": item.get("component_ref"),
            }
            for item in spec.declared_components()
        ],
        # Actual build adapters must flip this only after tests/signing complete.
        "artifact_ready": False,
    }
