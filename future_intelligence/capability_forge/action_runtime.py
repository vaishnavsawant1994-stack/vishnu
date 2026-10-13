from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from security.approvals import ApprovalManager, parameter_hash
from tools.registry import Risk


_GENERATED_METHOD_PREFIX = "qualified_generated_"
_MAX_CALLS = 16
_MAX_PLAN_BYTES = 1_000_000
_MAX_PARAMETER_NODES = 20_000


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _now() -> float:
    return time.time()


def _bounded_names(value: Any, *, limit: int = 64) -> tuple[str, ...]:
    if value is None:
        raw = ()
    elif isinstance(value, str):
        raw = (value,)
    elif isinstance(value, (list, tuple)):
        raw = value
    else:
        raise PermissionError("generated action permission list is invalid")
    out: list[str] = []
    for item in raw:
        clean = str(item or "").strip()
        if not clean or len(clean) > 1000:
            raise PermissionError("generated action contains an invalid permission value")
        if clean not in out:
            out.append(clean)
        if len(out) > limit:
            raise PermissionError("generated action permission list exceeds limit")
    return tuple(out)


def _walk_named_values(value: Any, *, keys: set[str]) -> list[str]:
    found: list[str] = []
    stack = [value]
    nodes = 0
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > _MAX_PARAMETER_NODES:
            raise ValueError("generated action parameters exceed structural limit")
        if isinstance(current, dict):
            for key, item in current.items():
                if str(key).casefold() in keys and item not in (None, "", [], {}):
                    if isinstance(item, (list, tuple, set)):
                        found.extend(str(x) for x in item)
                    elif not isinstance(item, dict):
                        found.append(str(item))
                stack.append(item)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    return found


def _path_within(value: str, roots: tuple[str, ...]) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or "://" in raw:
        return False
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    text = candidate.as_posix().lstrip("./")
    for root_raw in roots:
        root_path = PurePosixPath(str(root_raw).replace("\\", "/"))
        if root_path.is_absolute() or ".." in root_path.parts:
            continue
        root = root_path.as_posix().lstrip("./").rstrip("/")
        if root and (text == root or text.startswith(root + "/")):
            return True
    return False


def _host_within(value: str, hosts: tuple[str, ...]) -> bool:
    raw = str(value or "").strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").casefold().strip(".")
    return bool(host and any(host == allowed or host.endswith("." + allowed) for allowed in hosts))


class GeneratedActionService:
    """Stage and commit generated side effects through Vishnu's canonical authorities.

    Generated code can only *propose* an exact bounded call plan. Staging creates
    canonical ApprovalManager tickets for every side-effecting delegated call.
    Execution is a separate owner-driven commit after those exact tickets have
    been approved. ToolRegistry remains authoritative for contracts, effective
    risk, destinations, permissions, verification, emergency stop and rollback.
    """

    def __init__(self, path: str | Path, *, tools, approvals: ApprovalManager, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tools = tools
        self.approvals = approvals
        self.events = events
        self._init_db()

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS forge_action_proposals(
                    id TEXT PRIMARY KEY,
                    capability_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    device_id TEXT,
                    session_id TEXT,
                    data_classification TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    calls_json TEXT NOT NULL,
                    approvals_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forge_action_capability
                    ON forge_action_proposals(capability_id,created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_forge_action_state
                    ON forge_action_proposals(state,updated_at DESC);
                """
            )

    def _emit(self, name: str, **payload: Any) -> None:
        if self.events is not None:
            self.events.emit(name, **payload)

    @staticmethod
    def _max_risk(manifest: dict[str, Any]) -> Risk:
        value = str(manifest.get("risk") or "").casefold()
        if value == "read":
            return Risk.READ_ONLY
        if value == "write":
            return Risk.EXTERNAL_SIDE_EFFECT
        if value == "destructive":
            return Risk.DESTRUCTIVE
        raise PermissionError("generated action manifest has unsupported risk")

    def _tool_and_risk(self, manifest: dict[str, Any], name: str, parameters: dict[str, Any]):
        permissions = dict(manifest.get("permissions") or {})
        allowed_tools = frozenset(_bounded_names(permissions.get("allowed_tools"), limit=32))
        if name not in allowed_tools:
            raise PermissionError("generated action requested a tool outside its immutable allowlist")
        if name == str(manifest.get("id") or ""):
            raise PermissionError("generated action cannot recursively invoke itself")
        try:
            tool = self.tools.get(name)
        except (KeyError, TypeError) as exc:
            raise PermissionError("allowlisted generated action tool is unavailable") from exc
        if str(getattr(tool, "verification_method", "") or "").startswith(_GENERATED_METHOD_PREFIX):
            raise PermissionError("generated capabilities cannot delegate to generated capabilities")
        connector_id = str(getattr(tool, "connector_id", None) or "").strip()
        connectors = frozenset(_bounded_names(permissions.get("connector_ids")))
        if connector_id and connector_id not in connectors:
            raise PermissionError("delegated connector is outside the Forge specification")

        effective = self.tools.effective_risk(tool, parameters=parameters, data_classification="internal")
        effective = Risk(max(int(effective), int(getattr(tool, "minimum_risk", Risk.READ_ONLY) or Risk.READ_ONLY)))
        if effective is Risk.CRITICAL:
            raise PermissionError("critical generated actions remain disabled in Forge V2")
        if int(effective) > int(self._max_risk(manifest)):
            raise PermissionError("delegated action exceeds the qualified Forge risk ceiling")
        if effective is not Risk.READ_ONLY and not (
            bool(getattr(tool, "verification_required", False)) or callable(getattr(tool, "verifier", None))
        ):
            raise PermissionError("side-effecting generated actions require a verification contract")
        self._validate_scope(manifest, parameters, effective)
        return tool, effective

    @staticmethod
    def _validate_scope(manifest: dict[str, Any], parameters: dict[str, Any], risk: Risk) -> None:
        permissions = dict(manifest.get("permissions") or {})
        if permissions.get("secret_names"):
            raise PermissionError("raw secret access is not available to generated actions")
        hosts = tuple(x.casefold().strip(".") for x in _bounded_names(permissions.get("network_hosts")))
        read_roots = _bounded_names(permissions.get("filesystem_read"))
        write_roots = _bounded_names(permissions.get("filesystem_write"))
        for value in _walk_named_values(parameters, keys={"url", "domain"}):
            if not hosts or not _host_within(value, hosts):
                raise PermissionError("generated action network destination is outside the Forge host scope")
        roots = read_roots if risk is Risk.READ_ONLY else write_roots
        for value in _walk_named_values(parameters, keys={"path", "file_path", "filepath"}):
            if not roots or not _path_within(value, roots):
                label = "read" if risk is Risk.READ_ONLY else "write"
                raise PermissionError(f"generated action file path is outside the Forge {label} scope")

    @staticmethod
    def _normalize_calls(calls: Any) -> list[dict[str, Any]]:
        if not isinstance(calls, list) or not calls:
            raise ValueError("generated action plan requires a non-empty calls array")
        if len(calls) > _MAX_CALLS:
            raise PermissionError("generated action requested too many delegated calls")
        out: list[dict[str, Any]] = []
        for call in calls:
            if not isinstance(call, dict):
                raise ValueError("generated action call must be an object")
            name = str(call.get("tool") or "").strip()
            parameters = call.get("parameters", {})
            if not name or not isinstance(parameters, dict):
                raise ValueError("generated action call requires tool and object parameters")
            out.append({"tool": name, "parameters": parameters})
        encoded = _canonical(out).encode("utf-8")
        if len(encoded) > _MAX_PLAN_BYTES:
            raise ValueError("generated action plan exceeds the bounded payload quota")
        return out

    def stage(
        self,
        *,
        manifest: dict[str, Any],
        manifest_digest: str,
        parameters: dict[str, Any],
        calls: Any,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
        data_classification: str = "internal",
    ) -> dict[str, Any]:
        if str(manifest.get("runtime") or "") != "governed_action_v2":
            raise PermissionError("manifest is not a governed generated action")
        if not isinstance(parameters, dict):
            raise ValueError("generated action parameters must be an object")
        normalized = self._normalize_calls(calls)
        proposal_id = f"forge-action-{uuid.uuid4().hex}"
        execution_id = f"forge-action:{proposal_id}"
        approvals: list[dict[str, Any]] = []
        materialized: list[dict[str, Any]] = []
        created_ticket_ids: list[str] = []
        try:
            for index, call in enumerate(normalized):
                tool, risk = self._tool_and_risk(manifest, call["tool"], call["parameters"])
                destination = self.tools.destination(call["parameters"])
                ticket_id = None
                if risk is not Risk.READ_ONLY:
                    ticket = self.approvals.create(
                        execution_id,
                        tool.name,
                        call["parameters"],
                        owner_id=owner_id,
                        device_id=device_id,
                        session_id=session_id,
                        destination=destination,
                        data_classification=data_classification,
                    )
                    ticket_id = ticket.id
                    created_ticket_ids.append(ticket.id)
                    self.approvals.save_context(ticket.id, {
                        "approval_kind": "capability_forge_action",
                        "proposal_id": proposal_id,
                        "call_index": index,
                    })
                    approvals.append({
                        "call_index": index,
                        "approval_id": ticket.id,
                        "tool": tool.name,
                        "expires_at": ticket.expires_at,
                        "risk": risk.name,
                        "destination": destination,
                    })
                materialized.append({
                    "index": index,
                    "tool": tool.name,
                    "parameters": call["parameters"],
                    "parameter_hash": parameter_hash(call["parameters"]),
                    "risk": risk.name,
                    "destination": destination,
                    "approval_id": ticket_id,
                })
        except Exception:
            for ticket_id in created_ticket_ids:
                self.approvals.invalidate(ticket_id, code="forge_action_staging_failed")
            raise

        now = _now()
        with self._con() as con:
            con.execute(
                """INSERT INTO forge_action_proposals(
                    id,capability_id,version,manifest_digest,owner_id,device_id,session_id,
                    data_classification,parameters_json,calls_json,approvals_json,state,
                    result_json,error_code,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'waiting_approval',NULL,NULL,?,?)""",
                (
                    proposal_id, str(manifest.get("id") or ""), str(manifest.get("version") or ""),
                    str(manifest_digest), str(owner_id or "owner"), device_id, session_id,
                    str(data_classification or "internal"), _canonical(parameters),
                    _canonical(materialized), _canonical(approvals), now, now,
                ),
            )
        self._emit("capability_forge.action_staged", proposal_id=proposal_id, capability_id=manifest.get("id"), approvals=len(approvals))
        return self.get(proposal_id)

    def get(self, proposal_id: str) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute("SELECT * FROM forge_action_proposals WHERE id=?", (str(proposal_id),)).fetchone()
        if row is None:
            raise KeyError("Forge action proposal not found")
        item = dict(row)
        for source, target in (("parameters_json", "parameters"), ("calls_json", "calls"), ("approvals_json", "approvals"), ("result_json", "result")):
            raw = item.pop(source)
            item[target] = json.loads(raw) if raw else None
        return item

    def list(self, *, capability_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._con() as con:
            if capability_id:
                rows = con.execute(
                    "SELECT id FROM forge_action_proposals WHERE capability_id=? ORDER BY created_at DESC LIMIT ?",
                    (str(capability_id), limit),
                ).fetchall()
            else:
                rows = con.execute("SELECT id FROM forge_action_proposals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self.get(row["id"]) for row in rows]

    def approve_ticket(self, approval_id: str, *, owner_id: str, device_id: str | None, session_id: str | None) -> dict[str, Any]:
        context = self.approvals.context(str(approval_id))
        if not context or context.get("approval_kind") != "capability_forge_action":
            raise KeyError("Forge action approval not found")
        proposal = self.get(str(context["proposal_id"]))
        index = int(context["call_index"])
        call = next((item for item in proposal["calls"] if int(item["index"]) == index), None)
        if call is None or call.get("approval_id") != approval_id:
            raise PermissionError("Forge action approval lineage mismatch")
        decided = self.approvals.approve(
            approval_id,
            f"forge-action:{proposal['id']}",
            call["tool"],
            call["parameters"],
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=call["destination"],
            data_classification=proposal["data_classification"],
        )
        self._emit("capability_forge.action_approved", proposal_id=proposal["id"], approval_id=approval_id, call_index=index)
        return {"proposal_id": proposal["id"], "approval_id": approval_id, "status": decided["status"]}

    def reject_ticket(self, approval_id: str, *, device_id: str | None, session_id: str | None) -> bool:
        context = self.approvals.context(str(approval_id))
        if not context or context.get("approval_kind") != "capability_forge_action":
            return False
        proposal_id = str(context["proposal_id"])
        ok = self.approvals.reject(approval_id, device_id=device_id, session_id=session_id)
        if ok:
            self._set_state(proposal_id, "rejected", error_code="owner_rejected")
            self._emit("capability_forge.action_rejected", proposal_id=proposal_id, approval_id=approval_id)
        return ok

    def _set_state(self, proposal_id: str, state: str, *, result: Any = None, error_code: str | None = None) -> None:
        with self._con() as con:
            con.execute(
                "UPDATE forge_action_proposals SET state=?,result_json=?,error_code=?,updated_at=? WHERE id=?",
                (str(state), _canonical(result) if result is not None else None, error_code, _now(), str(proposal_id)),
            )

    @staticmethod
    def _fresh(stamp: float | None, *, ttl: int = 300) -> bool:
        if stamp is None:
            return False
        try:
            age = _now() - float(stamp)
        except (TypeError, ValueError):
            return False
        return 0 <= age <= ttl

    def commit(
        self,
        proposal_id: str,
        *,
        manifest: dict[str, Any],
        manifest_digest: str,
        owner_id: str,
        device_id: str | None,
        session_id: str | None,
        reauthenticated_at: float | None = None,
    ) -> dict[str, Any]:
        proposal = self.get(proposal_id)
        if proposal["state"] not in {"waiting_approval", "ready"}:
            raise PermissionError(f"Forge action proposal is {proposal['state']}")
        if proposal["manifest_digest"] != str(manifest_digest) or proposal["capability_id"] != str(manifest.get("id") or ""):
            raise PermissionError("Forge action manifest lineage changed after staging")
        if proposal["owner_id"] != str(owner_id or "owner"):
            raise PermissionError("Forge action owner mismatch")
        if proposal["device_id"] is not None and proposal["device_id"] != device_id:
            raise PermissionError("Forge action device mismatch")
        if proposal["session_id"] is not None and proposal["session_id"] != session_id:
            raise PermissionError("Forge action session mismatch")

        # Preflight every call again against the live registry and exact frozen parameters.
        live: list[tuple[dict[str, Any], Any, Risk]] = []
        for call in proposal["calls"]:
            if call["parameter_hash"] != parameter_hash(call["parameters"]):
                raise PermissionError("Forge action parameters changed after approval staging")
            tool, risk = self._tool_and_risk(manifest, call["tool"], call["parameters"])
            if risk.name != call["risk"] or self.tools.destination(call["parameters"]) != call["destination"]:
                raise PermissionError("Forge action authority changed after staging")
            if (getattr(tool, "requires_reauth", False) or risk >= Risk.DESTRUCTIVE) and not self._fresh(reauthenticated_at):
                raise PermissionError("recent owner reauthentication is required for this generated action")
            if risk is Risk.READ_ONLY:
                decision = self.tools.authorize(tool, confirmed=False, parameters=call["parameters"], data_classification=proposal["data_classification"])
                if not getattr(decision, "allowed", False) or getattr(decision, "requires_confirmation", False):
                    raise PermissionError("read step is not currently authorized")
            else:
                record = self.approvals.record(str(call["approval_id"]))
                if not record or record.get("status") != "approved":
                    raise PermissionError("all side-effecting generated action approvals must be approved before commit")
                decision = self.tools.authorize(tool, confirmed=True, parameters=call["parameters"], data_classification=proposal["data_classification"])
                if not getattr(decision, "allowed", False):
                    raise PermissionError("generated action no longer passes live owner policy")
            live.append((call, tool, risk))

        self._set_state(proposal_id, "executing")
        completed: list[dict[str, Any]] = []
        current_ticket: str | None = None
        try:
            for call, tool, risk in live:
                current_ticket = str(call.get("approval_id") or "") or None
                if current_ticket:
                    lease = self.approvals.begin_dispatch(current_ticket, worker_id=f"forge-action:{proposal_id}")
                    if not lease.get("dispatch"):
                        if lease.get("status") == "completed":
                            completed.append({"call": call, "tool": tool, "risk": risk, "result": (lease.get("outcome") or {}).get("result"), "replayed": True})
                            continue
                        raise PermissionError(f"generated action approval is {lease.get('status')}")
                result = self.tools.dispatch(tool, call["parameters"])
                verification = self.tools.verify_result(tool, call["parameters"], result)
                if not verification.verified:
                    raise RuntimeError("generated action verification failed")
                record = {"call": call, "tool": tool, "risk": risk, "result": result, "replayed": False}
                completed.append(record)
                if current_ticket:
                    self.approvals.complete_dispatch(current_ticket, {
                        "verified": True,
                        "verification_reason": verification.reason,
                        "result": result,
                    })
                current_ticket = None
        except Exception as exc:
            if current_ticket:
                self.approvals.mark_recovery_required(current_ticket, code="forge_action_dispatch_uncertain")
            rollback_results: list[dict[str, Any]] = []
            recovery_required = bool(current_ticket)
            for item in reversed(completed):
                tool = item["tool"]
                if item.get("replayed"):
                    recovery_required = True
                    rollback_results.append({"tool": tool.name, "ok": False, "reason": "replayed prior dispatch requires recovery review"})
                    continue
                rollback = getattr(tool, "rollback", None)
                if not callable(rollback):
                    if item["risk"] is not Risk.READ_ONLY:
                        recovery_required = True
                    rollback_results.append({"tool": tool.name, "ok": item["risk"] is Risk.READ_ONLY, "reason": "no rollback contract"})
                    continue
                try:
                    rollback(item["call"]["parameters"], item["result"])
                    rollback_results.append({"tool": tool.name, "ok": True})
                except Exception as rollback_exc:
                    recovery_required = True
                    rollback_results.append({"tool": tool.name, "ok": False, "reason": type(rollback_exc).__name__})
            state = "recovery_required" if recovery_required else "rolled_back"
            failure = {"error_type": type(exc).__name__, "rollback": rollback_results}
            self._set_state(proposal_id, state, result=failure, error_code="dispatch_failed")
            self._emit("capability_forge.action_failed", proposal_id=proposal_id, state=state, error_type=type(exc).__name__)
            raise

        safe_results = [{"index": item["call"]["index"], "tool": item["tool"].name, "result": item["result"]} for item in completed]
        self._set_state(proposal_id, "completed", result={"results": safe_results})
        self._emit("capability_forge.action_completed", proposal_id=proposal_id, capability_id=proposal["capability_id"], calls=len(safe_results))
        return self.get(proposal_id)

    def cancel(self, proposal_id: str, *, device_id: str | None, session_id: str | None) -> dict[str, Any]:
        proposal = self.get(proposal_id)
        if proposal["state"] not in {"waiting_approval", "ready"}:
            raise PermissionError("only uncommitted Forge action proposals can be cancelled")
        for call in proposal["calls"]:
            ticket_id = call.get("approval_id")
            if ticket_id:
                record = self.approvals.record(str(ticket_id))
                if record and record.get("status") == "pending":
                    self.approvals.reject(str(ticket_id), device_id=device_id, session_id=session_id)
                elif record and record.get("status") == "approved":
                    self.approvals.invalidate(str(ticket_id), code="forge_action_cancelled")
        self._set_state(proposal_id, "cancelled", error_code="owner_cancelled")
        self._emit("capability_forge.action_cancelled", proposal_id=proposal_id)
        return self.get(proposal_id)
