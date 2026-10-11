from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
from typing import Any, Protocol
from uuid import uuid4

from training.self_improvement import TrainedModelStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized(value: str, fallback: str) -> str:
    return str(value or "").strip().lower() or fallback


class ActiveModelRegistry(Protocol):
    def get_model(self, model_id: str): ...


@dataclass(frozen=True)
class SpecialistBinding:
    binding_id: str
    specialist_role: str
    task_domain: str
    model_id: str
    checkpoint_ref: str
    base_model: str
    method: str
    bound_at: str
    superseded_at: str | None = None

    @property
    def active(self) -> bool:
        return self.superseded_at is None

    def public(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "specialist_role": self.specialist_role,
            "task_domain": self.task_domain,
            "model_id": self.model_id,
            "checkpoint_ref": self.checkpoint_ref,
            "base_model": self.base_model,
            "method": self.method,
            "bound_at": self.bound_at,
            "superseded_at": self.superseded_at,
            "active": self.active,
            "promotion_authority": False,
        }


class SpecialistAdapterRegistry:
    """Role/domain projection over the canonical trained-model registry.

    This registry cannot approve, promote, deploy or activate a model. It may
    bind only a model that the canonical training registry already reports as
    ACTIVE. Resolution re-checks that status every time, so a stale/rolled-back
    model cannot remain eligible merely because an old specialist binding exists.
    """

    def __init__(self, path: str | Path, models: ActiveModelRegistry) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.models = models
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS specialist_bindings(
                    binding_id TEXT PRIMARY KEY,
                    specialist_role TEXT NOT NULL,
                    task_domain TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    checkpoint_ref TEXT NOT NULL,
                    base_model TEXT NOT NULL,
                    method TEXT NOT NULL,
                    bound_at TEXT NOT NULL,
                    superseded_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_specialist_active
                ON specialist_bindings(specialist_role, task_domain)
                WHERE superseded_at IS NULL;
                CREATE INDEX IF NOT EXISTS idx_specialist_model
                ON specialist_bindings(model_id, superseded_at);
                """
            )

    @staticmethod
    def _binding(row: sqlite3.Row) -> SpecialistBinding:
        return SpecialistBinding(
            binding_id=str(row["binding_id"]),
            specialist_role=str(row["specialist_role"]),
            task_domain=str(row["task_domain"]),
            model_id=str(row["model_id"]),
            checkpoint_ref=str(row["checkpoint_ref"]),
            base_model=str(row["base_model"]),
            method=str(row["method"]),
            bound_at=str(row["bound_at"]),
            superseded_at=row["superseded_at"],
        )

    @staticmethod
    def _canonical_owner(owner_id: str) -> None:
        if str(owner_id or "") != "owner":
            raise PermissionError("only the canonical owner may change specialist model bindings")

    def _require_active_model(self, model_id: str):
        model = self.models.get_model(str(model_id))
        if model is None:
            raise KeyError(model_id)
        status = getattr(model, "status", None)
        if status is not TrainedModelStatus.ACTIVE and str(getattr(status, "value", status)) != TrainedModelStatus.ACTIVE.value:
            raise ValueError("specialist binding requires a production-active trained model")
        checkpoint_ref = str(getattr(model, "checkpoint_ref", "") or "")
        if not checkpoint_ref:
            raise RuntimeError("active trained model is missing checkpoint_ref")
        return model

    def bind(
        self,
        *,
        owner_id: str,
        specialist_role: str,
        task_domain: str = "general",
        model_id: str,
    ) -> SpecialistBinding:
        self._canonical_owner(owner_id)
        role = _normalized(specialist_role, "general")
        domain = _normalized(task_domain, "general")
        if role == "general":
            raise ValueError("specialist_role must identify a specialist")
        model = self._require_active_model(model_id)
        stamp = _now()
        binding_id = f"specialist-{uuid4().hex[:20]}"
        with self._lock, self.connection:
            self.connection.execute(
                """UPDATE specialist_bindings
                   SET superseded_at=?
                   WHERE specialist_role=? AND task_domain=? AND superseded_at IS NULL""",
                (stamp, role, domain),
            )
            self.connection.execute(
                """INSERT INTO specialist_bindings(
                    binding_id,specialist_role,task_domain,model_id,checkpoint_ref,
                    base_model,method,bound_at,superseded_at
                ) VALUES(?,?,?,?,?,?,?,?,NULL)""",
                (
                    binding_id,
                    role,
                    domain,
                    str(model.model_id),
                    str(model.checkpoint_ref),
                    str(model.base_model),
                    str(model.method),
                    stamp,
                ),
            )
        binding = self.get(binding_id)
        if binding is None:
            raise RuntimeError("specialist binding was not persisted")
        return binding

    def get(self, binding_id: str) -> SpecialistBinding | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM specialist_bindings WHERE binding_id=?",
                (str(binding_id),),
            ).fetchone()
        return None if row is None else self._binding(row)

    def resolve(self, specialist_role: str, task_domain: str = "general") -> SpecialistBinding | None:
        role = _normalized(specialist_role, "general")
        domain = _normalized(task_domain, "general")
        with self._lock:
            row = self.connection.execute(
                """SELECT * FROM specialist_bindings
                   WHERE specialist_role=? AND task_domain=? AND superseded_at IS NULL""",
                (role, domain),
            ).fetchone()
            if row is None and domain != "general":
                row = self.connection.execute(
                    """SELECT * FROM specialist_bindings
                       WHERE specialist_role=? AND task_domain='general' AND superseded_at IS NULL""",
                    (role,),
                ).fetchone()
        if row is None:
            return None
        binding = self._binding(row)
        try:
            model = self._require_active_model(binding.model_id)
        except (KeyError, ValueError, RuntimeError):
            return None
        if str(model.checkpoint_ref) != binding.checkpoint_ref:
            return None
        return binding

    def unbind(self, *, owner_id: str, specialist_role: str, task_domain: str = "general") -> bool:
        self._canonical_owner(owner_id)
        role = _normalized(specialist_role, "general")
        domain = _normalized(task_domain, "general")
        with self._lock, self.connection:
            cursor = self.connection.execute(
                """UPDATE specialist_bindings SET superseded_at=?
                   WHERE specialist_role=? AND task_domain=? AND superseded_at IS NULL""",
                (_now(), role, domain),
            )
        return bool(cursor.rowcount)

    def active_bindings(self) -> tuple[SpecialistBinding, ...]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM specialist_bindings WHERE superseded_at IS NULL ORDER BY specialist_role,task_domain"
            ).fetchall()
        result: list[SpecialistBinding] = []
        for row in rows:
            binding = self._binding(row)
            resolved = self.resolve(binding.specialist_role, binding.task_domain)
            if resolved is not None and resolved.binding_id == binding.binding_id:
                result.append(binding)
        return tuple(result)

    def history(self, *, limit: int = 100) -> tuple[SpecialistBinding, ...]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM specialist_bindings ORDER BY bound_at DESC LIMIT ?",
                (max(1, min(1000, int(limit))),),
            ).fetchall()
        return tuple(self._binding(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self.connection.close()
