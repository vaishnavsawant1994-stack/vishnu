from __future__ import annotations

import json
from typing import Mapping

from models.contracts import ModelRequest
from models.router import InvalidModelResponse


def governed_engineering_json(models, *, spec, prompt: str, system: str, role: str) -> Mapping[str, object]:
    """Use the Intelligence Fabric typed request path when available.

    This binds engineering model calls to the Canonical Work/Attempt and applies
    the owner per-Work model cost ceiling through ModelRequest.max_cost. Simple
    `.json()` model doubles remain supported for deterministic unit tests.
    """
    max_cost = spec.metadata.get("max_model_cost_per_work") if isinstance(spec.metadata, Mapping) else None
    if hasattr(models, "request"):
        request = ModelRequest(
            prompt=str(prompt),
            system=str(system),
            execution_id=f"engineering:{spec.attempt_id}",
            task_id=spec.work_order_id,
            agent_id=str(role),
            project_id=(str(spec.metadata.get("project_id")) if isinstance(spec.metadata, Mapping) and spec.metadata.get("project_id") else None),
            capability="chat",
            routing_policy="coding" if role != "independent-engineering-reviewer" else "review",
            required_capabilities=("chat",),
            preferred_capabilities=("json",),
            sensitivity="internal",
            max_cost=(None if max_cost in {None, ""} else float(max_cost)),
            metadata={
                "temperature": 0.1,
                "engineering_spec_id": spec.id,
                "model_output_authority": False,
                "engineering_role": str(role),
            },
        )
        response = models.request(request)
        raw = str(response.content or "").strip()
        fence = "```"
        if raw.startswith(fence):
            raw = raw.replace(fence + "json", "").replace(fence, "").strip()
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise InvalidModelResponse("Engineering model did not return valid JSON", provider=response.provider_id) from exc
        if not isinstance(payload, Mapping):
            raise InvalidModelResponse("Engineering model JSON must be an object", provider=response.provider_id)
        return payload
    payload = models.json(prompt, system=system, sensitivity="internal")
    if not isinstance(payload, Mapping):
        raise ValueError("engineering model did not return an object")
    return payload
