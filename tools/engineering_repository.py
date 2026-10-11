from __future__ import annotations

from tools.registry import Risk, Tool, VerificationResult


_IDENTITY = {
    "type": "object",
    "required": ["work_order_id", "attempt_id"],
    "properties": {
        "work_order_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "attempt_id": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}


def _schema(properties, required=()):
    merged = dict(_IDENTITY["properties"])
    merged.update(properties)
    return {
        "type": "object",
        "required": ["work_order_id", "attempt_id", *required],
        "properties": merged,
        "additionalProperties": False,
    }


def _call(runtime, operation):
    def handler(params):
        payload = dict(params)
        work_order_id = payload.pop("work_order_id")
        attempt_id = payload.pop("attempt_id")
        return runtime.execute(work_order_id, attempt_id, operation, payload)
    return handler


def _mutation_verifier(_params, result):
    verified = bool(isinstance(result, dict) and result.get("verified_scope") is True and result.get("mutations"))
    return VerificationResult(
        verified=verified,
        reason="isolated engineering workspace mutation recorded" if verified else "engineering mutation evidence is missing",
        evidence={
            "mutated_paths": list((result or {}).get("mutated_paths") or []) if isinstance(result, dict) else [],
            "remote_mutation": False,
        },
    )


def register(registry, runtime):
    """Register model-visible source operations bound to Canonical Work.

    The handlers accept Work/Attempt identity but never a filesystem root,
    repository root, branch root, remote, credential, shell command, merge, or
    deployment target. EngineeringRuntime resolves the durable workspace and
    fails closed unless the matching attempt owns the active Work lease.
    """
    result_schema = {"type": "object"}
    path = {"type": "string", "minLength": 1, "maxLength": 1000}
    sha = {"type": "string", "minLength": 64, "maxLength": 64}
    content = {"type": "string", "maxLength": 5_000_000}

    registry.register(Tool(
        "repository_read",
        "Read UTF-8 source from the active isolated engineering Work/Attempt workspace",
        _call(runtime, "read"),
        Risk.READ_ONLY,
        input_schema=_schema({"path": path}, ("path",)),
        output_schema=result_schema,
        verification_method="workspace_bound_read",
    ))
    registry.register(Tool(
        "repository_search",
        "Search source text inside the active isolated engineering Work/Attempt workspace",
        _call(runtime, "search"),
        Risk.READ_ONLY,
        input_schema=_schema({
            "query": {"type": "string", "minLength": 1, "maxLength": 2000},
            "paths": {"type": "array", "maxItems": 100, "items": path},
            "case_sensitive": {"type": "boolean"},
        }, ("query",)),
        output_schema=result_schema,
        verification_method="workspace_bound_search",
    ))
    registry.register(Tool(
        "repository_diff",
        "Read the base-to-working diff for one governed source path",
        _call(runtime, "diff"),
        Risk.READ_ONLY,
        input_schema=_schema({"path": path}, ("path",)),
        output_schema=result_schema,
        verification_method="workspace_bound_diff",
    ))
    registry.register(Tool(
        "repository_status",
        "Inspect the active engineering workspace status without remote mutation authority",
        _call(runtime, "status"),
        Risk.READ_ONLY,
        input_schema=_schema({}, ()),
        output_schema=result_schema,
        verification_method="workspace_bound_status",
    ))

    registry.register(Tool(
        "repository_create_file",
        "Create a UTF-8 source file inside the allowed engineering workspace scope",
        _call(runtime, "create"),
        Risk.REVERSIBLE,
        verifier=_mutation_verifier,
        verification_required=True,
        input_schema=_schema({"path": path, "content": content}, ("path", "content")),
        output_schema=result_schema,
        idempotency_supported=False,
        verification_method="mutation_evidence",
    ))
    registry.register(Tool(
        "repository_modify_file",
        "Replace a governed UTF-8 source file using a required stale-write SHA-256 precondition",
        _call(runtime, "replace"),
        Risk.REVERSIBLE,
        verifier=_mutation_verifier,
        verification_required=True,
        input_schema=_schema({"path": path, "content": content, "expected_sha256": sha}, ("path", "content", "expected_sha256")),
        output_schema=result_schema,
        idempotency_supported=False,
        verification_method="mutation_evidence",
    ))
    registry.register(Tool(
        "repository_apply_patch",
        "Apply one exact old-to-new source replacement with a stale-write SHA-256 precondition",
        _call(runtime, "replace_exact"),
        Risk.REVERSIBLE,
        verifier=_mutation_verifier,
        verification_required=True,
        input_schema=_schema({
            "path": path,
            "old": {"type": "string", "minLength": 1, "maxLength": 2_000_000},
            "new": {"type": "string", "maxLength": 2_000_000},
            "expected_sha256": sha,
        }, ("path", "old", "new", "expected_sha256")),
        output_schema=result_schema,
        idempotency_supported=False,
        verification_method="mutation_evidence",
    ))
    registry.register(Tool(
        "repository_delete_file",
        "Delete one allowed engineering source file with a stale-write SHA-256 precondition",
        _call(runtime, "delete"),
        Risk.REVERSIBLE,
        verifier=_mutation_verifier,
        verification_required=True,
        input_schema=_schema({"path": path, "expected_sha256": sha}, ("path", "expected_sha256")),
        output_schema=result_schema,
        idempotency_supported=False,
        verification_method="mutation_evidence",
    ))
    registry.register(Tool(
        "repository_rename_file",
        "Rename one allowed engineering source file inside the same isolated workspace",
        _call(runtime, "rename"),
        Risk.REVERSIBLE,
        verifier=_mutation_verifier,
        verification_required=True,
        input_schema=_schema({"source": path, "destination": path, "expected_sha256": sha}, ("source", "destination", "expected_sha256")),
        output_schema=result_schema,
        idempotency_supported=False,
        verification_method="mutation_evidence",
    ))
    registry.register(Tool(
        "repository_restore_file",
        "Restore one allowed source path from the engineering workspace base revision",
        _call(runtime, "restore"),
        Risk.REVERSIBLE,
        verifier=_mutation_verifier,
        verification_required=True,
        input_schema=_schema({"path": path}, ("path",)),
        output_schema=result_schema,
        idempotency_supported=False,
        verification_method="mutation_evidence",
    ))
