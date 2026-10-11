from __future__ import annotations

from copy import deepcopy

from .models import AI_MODES, ensure_choice


_PROVIDER_MODES = {"openai", "anthropic", "gemini", "azure_openai", "openrouter", "openai_compatible", "custom"}
_PERMISSION_STATES = {"allow", "ask", "deny"}


def normalize_ai_policy(policy: dict | None) -> dict:
    value = deepcopy(policy or {})
    mode = ensure_choice(value.get("mode", "disabled"), AI_MODES, "AI mode")
    value["mode"] = mode

    if mode == "disabled":
        # No provider may be silently used when a product is explicitly no-AI.
        return {"mode": "disabled"}

    if mode == "client_api":
        provider = str(value.get("provider") or "").strip().lower()
        if provider and provider not in _PROVIDER_MODES:
            raise ValueError(f"Unsupported client AI provider: {provider}")
        secret_ref = str(value.get("secret_ref") or "").strip()
        if not secret_ref:
            raise ValueError("Client API mode requires secret_ref; raw API keys are never product configuration")
        result = {"mode": mode, "secret_ref": secret_ref[:300]}
        if provider:
            result["provider"] = provider
        if value.get("model"):
            result["model"] = str(value["model"])[:200]
        if value.get("endpoint"):
            result["endpoint"] = str(value["endpoint"])[:500]
        return result

    if mode == "managed":
        result = {"mode": mode, "route": str(value.get("route") or "default")[:120]}
        if value.get("monthly_budget") is not None:
            budget = float(value["monthly_budget"])
            if budget < 0:
                raise ValueError("monthly_budget cannot be negative")
            result["monthly_budget"] = budget
        return result

    if mode == "local":
        endpoint_ref = str(value.get("endpoint_ref") or "").strip()
        if not endpoint_ref:
            raise ValueError("Local AI mode requires endpoint_ref")
        return {
            "mode": mode,
            "endpoint_ref": endpoint_ref[:300],
            "model": str(value.get("model") or "auto")[:200],
        }

    # Hybrid policies route capability classes to named routes. Routes may point
    # to client, managed or local providers at runtime; credentials remain vault refs.
    routes = value.get("routes") or []
    if not isinstance(routes, list) or not routes:
        raise ValueError("Hybrid AI mode requires at least one route")
    normalized_routes = []
    for item in routes:
        if not isinstance(item, dict):
            raise ValueError("Hybrid routes must be objects")
        route_id = str(item.get("id") or "").strip()
        route_mode = str(item.get("mode") or "").strip()
        if not route_id or route_mode not in {"client_api", "managed", "local"}:
            raise ValueError("Each hybrid route requires an id and mode client_api/managed/local")
        normalized_routes.append({
            "id": route_id[:120],
            "mode": route_mode,
            "capabilities": [str(v)[:120] for v in (item.get("capabilities") or [])],
            "secret_ref": str(item.get("secret_ref") or "")[:300] or None,
            "endpoint_ref": str(item.get("endpoint_ref") or "")[:300] or None,
            "provider": str(item.get("provider") or "")[:120] or None,
            "model": str(item.get("model") or "")[:200] or None,
        })
    return {
        "mode": "hybrid",
        "routes": normalized_routes,
        "fallback_route": str(value.get("fallback_route") or normalized_routes[0]["id"])[:120],
    }


def normalize_permissions(permissions: dict | None) -> dict:
    """Normalize a product permission allow-list.

    Missing permissions are denied by the runtime. Every explicit capability is
    one of allow/ask/deny; exported runtimes never infer access from Vishnu's
    owner capabilities.
    """
    value = deepcopy(permissions or {})
    output = {}
    for capability, state in value.items():
        key = str(capability).strip()
        normalized = str(state).strip().lower()
        if not key:
            raise ValueError("Permission capability names cannot be empty")
        if normalized not in _PERMISSION_STATES:
            raise ValueError(f"Unsupported permission state for {key}: {state}")
        output[key] = normalized
    return output


def permission_state(permissions: dict, capability: str) -> str:
    return normalize_permissions(permissions).get(str(capability), "deny")
