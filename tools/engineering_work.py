from __future__ import annotations

from tools.registry import Risk, Tool, VerificationResult


def register(registry, executor, *, runtime_epoch_provider):
    """Register explicit owner-gated end-to-end engineering execution.

    The model may identify a Canonical WorkOrder, but it cannot choose a local
    filesystem root, repository remote, worker identity, runtime epoch, shell
    command, merge target, deployment target, or approval outcome.
    """

    def handler(params):
        work_order_id = str(params["work_order_id"])
        result = executor.execute(
            work_order_id,
            worker_id="vishnu-software-engineer",
            runtime_epoch=int(runtime_epoch_provider()),
            base_revision="HEAD",
        )
        return result.to_dict()

    def verifier(_params, result):
        safe = bool(
            isinstance(result, dict)
            and result.get("candidate_revision")
            and result.get("status") in {"verifying", "qualified"}
            and result.get("push_authority") is False
            and result.get("merge_authority") is False
            and result.get("deploy_authority") is False
            and result.get("activation_authority") is False
        )
        return VerificationResult(
            verified=safe,
            reason=(
                "local engineering candidate created without remote/release authority"
                if safe else
                "engineering execution did not produce a bounded candidate result"
            ),
            evidence={
                "candidate_revision": result.get("candidate_revision") if isinstance(result, dict) else None,
                "status": result.get("status") if isinstance(result, dict) else None,
                "remote_mutation_authority": False,
            },
        )

    registry.register(Tool(
        name="engineering_execute_work",
        description=(
            "Execute an owner-approved Canonical software-engineering WorkOrder through isolated repository editing, "
            "trusted verification, bounded repair and independent review; stops before push, merge or deploy"
        ),
        handler=handler,
        risk=Risk.CRITICAL,
        verifier=verifier,
        verification_required=True,
        requires_reauth=True,
        capability="execute governed engineering work",
        minimum_risk=Risk.CRITICAL,
        input_schema={
            "type": "object",
            "required": ["work_order_id"],
            "properties": {
                "work_order_id": {"type": "string", "minLength": 1, "maxLength": 200},
            },
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        idempotency_supported=False,
        verification_method="candidate_revision_and_no_remote_authority",
    ))
