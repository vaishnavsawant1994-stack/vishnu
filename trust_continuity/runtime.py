from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .adapters import KeychainSecretStore, VerifiedOAuthLifecycleManager
from .future_extensions import GovernedFutureCapabilities
from .identity_continuity import MultiDeviceContinuity, UniversalOwnerRecovery
from .memory_intelligence import MemoryIntelligence
from .operations import OperationalHealthMonitor
from .production import (
    DeploymentTransaction,
    PhysicalL4Qualification,
    ProductionReadinessManager,
)
from .services import EvaluationLab, OfflineIntelligence, TrustCenter
from .store import TrustContinuityStore
from .work_engine import WorkEngineV2


@dataclass
class TrustContinuityRuntime:
    owner_id: str
    store: TrustContinuityStore
    readiness: ProductionReadinessManager
    l4: PhysicalL4Qualification
    deployment: DeploymentTransaction
    health: OperationalHealthMonitor
    continuity: MultiDeviceContinuity
    work: WorkEngineV2
    memory: MemoryIntelligence
    offline: OfflineIntelligence
    evaluation: EvaluationLab
    future: GovernedFutureCapabilities
    # In full Vishnu composition this points at the existing canonical OAuth
    # authority. The provider-neutral fallback exists only for reduced runtimes.
    oauth: Any = None
    recovery: UniversalOwnerRecovery | None = None
    trust_center: TrustCenter | None = None

    def status(self) -> dict[str, Any]:
        return {
            "owner_identity_bound": bool(self.owner_id),
            "readiness": self.readiness.readiness().as_dict(),
            "l4": self.l4.platform_status(),
            "execution_authority": False,
            "oauth_available": self.oauth is not None,
            "recovery_available": self.recovery is not None,
            "trust_center_available": self.trust_center is not None,
        }


def build_trust_continuity_runtime(
    *,
    data_dir: str | Path,
    commit_sha: str,
    owner_id: str = "owner",
    is_trusted_device: Callable[[str], bool],
    approval_check: Callable[[str, dict[str, Any]], bool] | None = None,
    proposal_approval_check: Callable[[str], bool] | None = None,
    oauth_manager: Any = None,
    keychain=None,
    owner_authenticator: Callable[[str, str, str], bool] | None = None,
    register_device: Callable[[str, dict[str, Any]], str | dict[str, Any]] | None = None,
    revoke_device: Callable[[str], None] | None = None,
    stop_sensing: Callable[[], None] | None = None,
    stop_actions: Callable[[], None] | None = None,
    disconnect_provider: Callable[[str], None] | None = None,
    emergency_stop: Callable[[bool], None] | None = None,
    snapshot_sources: dict[str, Callable[[], Any]] | None = None,
) -> TrustContinuityRuntime:
    """Compose the campaign without replacing canonical Vishnu authorities.

    Optional security-sensitive services stay unavailable until their canonical
    callbacks are explicitly supplied. Defaults never grant action authority.
    A full Vishnu runtime supplies its existing OAuth manager; the keychain-backed
    provider-neutral lifecycle is retained only for reduced/test compositions.
    """

    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    store = TrustContinuityStore(root / "trust-continuity.sqlite3")
    runtime = TrustContinuityRuntime(
        owner_id=str(owner_id or "owner"),
        store=store,
        readiness=ProductionReadinessManager(store, commit_sha=commit_sha),
        l4=PhysicalL4Qualification(store, commit_sha=commit_sha),
        deployment=DeploymentTransaction(store),
        health=OperationalHealthMonitor(store),
        continuity=MultiDeviceContinuity(
            store,
            is_trusted_device=is_trusted_device,
        ),
        work=WorkEngineV2(store, approval_check=approval_check),
        memory=MemoryIntelligence(store),
        offline=OfflineIntelligence(store),
        evaluation=EvaluationLab(store, commit_sha=commit_sha),
        future=GovernedFutureCapabilities(
            store,
            approval_check=proposal_approval_check,
        ),
    )

    if oauth_manager is not None:
        runtime.oauth = oauth_manager
    elif keychain is not None:
        runtime.oauth = VerifiedOAuthLifecycleManager(
            store,
            KeychainSecretStore(keychain),
        )

    recovery_callbacks = (owner_authenticator, register_device, revoke_device)
    if all(callback is not None for callback in recovery_callbacks):
        runtime.recovery = UniversalOwnerRecovery(
            store,
            owner_authenticator=owner_authenticator,
            register_device=register_device,
            revoke_device=revoke_device,
        )

    trust_callbacks = (
        stop_sensing,
        stop_actions,
        revoke_device,
        disconnect_provider,
        emergency_stop,
    )
    if all(callback is not None for callback in trust_callbacks):
        runtime.trust_center = TrustCenter(
            store,
            stop_sensing=stop_sensing,
            stop_actions=stop_actions,
            revoke_device=revoke_device,
            disconnect_provider=disconnect_provider,
            emergency_stop=emergency_stop,
            snapshot_sources=snapshot_sources,
        )
    return runtime