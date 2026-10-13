from __future__ import annotations

import re
from typing import Any


_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_ALLOWED_TYPES = frozenset({"string", "number", "integer", "boolean", "select", "multiline"})


class GeneratedUIContractError(ValueError):
    pass


def validate_generated_ui_contract(value: Any) -> dict[str, Any]:
    """Validate the intentionally code-free UI contract for a generated capability.

    Generated capability UI is declarative only. No HTML, JavaScript, remote
    assets, event handlers, URLs, CSS, or executable expressions are accepted.
    The trusted Vishnu owner console renders these fields using its own controls.
    """
    if not isinstance(value, dict):
        raise GeneratedUIContractError("generated UI contract must be an object")
    allowed_top = {"schema_version", "title", "description", "fields", "submit_label", "confirmation_text"}
    unknown = set(value) - allowed_top
    if unknown:
        raise GeneratedUIContractError(f"unsupported generated UI keys: {sorted(unknown)}")
    if int(value.get("schema_version", 1)) != 1:
        raise GeneratedUIContractError("unsupported generated UI schema version")
    title = " ".join(str(value.get("title") or "").split())[:120]
    if not title:
        raise GeneratedUIContractError("generated UI title is required")
    description = " ".join(str(value.get("description") or "").split())[:1000]
    submit_label = " ".join(str(value.get("submit_label") or "Run").split())[:80] or "Run"
    confirmation_text = " ".join(str(value.get("confirmation_text") or "").split())[:500]
    fields = value.get("fields") or []
    if not isinstance(fields, list) or len(fields) > 50:
        raise GeneratedUIContractError("generated UI fields must be a list of at most 50 items")
    names: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in fields:
        if not isinstance(raw, dict):
            raise GeneratedUIContractError("generated UI field must be an object")
        allowed_field = {"name", "label", "type", "required", "placeholder", "help", "options", "default", "min", "max"}
        extra = set(raw) - allowed_field
        if extra:
            raise GeneratedUIContractError(f"unsupported generated UI field keys: {sorted(extra)}")
        name = str(raw.get("name") or "").strip()
        if not _NAME_RE.fullmatch(name) or name in names:
            raise GeneratedUIContractError("generated UI field name is invalid or duplicated")
        names.add(name)
        field_type = str(raw.get("type") or "string").strip().casefold()
        if field_type not in _ALLOWED_TYPES:
            raise GeneratedUIContractError("generated UI field type is unsupported")
        label = " ".join(str(raw.get("label") or name).split())[:120]
        placeholder = " ".join(str(raw.get("placeholder") or "").split())[:200]
        help_text = " ".join(str(raw.get("help") or "").split())[:500]
        field: dict[str, Any] = {
            "name": name,
            "label": label,
            "type": field_type,
            "required": bool(raw.get("required", False)),
        }
        if placeholder:
            field["placeholder"] = placeholder
        if help_text:
            field["help"] = help_text
        if "default" in raw and raw.get("default") is not None:
            default = raw.get("default")
            if not isinstance(default, (str, int, float, bool)):
                raise GeneratedUIContractError("generated UI default must be scalar")
            field["default"] = default
        if field_type == "select":
            options = raw.get("options") or []
            if not isinstance(options, list) or not 1 <= len(options) <= 100:
                raise GeneratedUIContractError("generated UI select requires 1-100 options")
            clean_options: list[str] = []
            for option in options:
                item = " ".join(str(option or "").split())[:160]
                if not item or item in clean_options:
                    raise GeneratedUIContractError("generated UI select option is invalid or duplicated")
                clean_options.append(item)
            field["options"] = clean_options
        elif raw.get("options") not in (None, []):
            raise GeneratedUIContractError("options are allowed only for select fields")
        if field_type in {"number", "integer"}:
            for key in ("min", "max"):
                if key in raw and raw.get(key) is not None:
                    candidate = raw[key]
                    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
                        raise GeneratedUIContractError("numeric generated UI bounds must be numbers")
                    field[key] = candidate
            if "min" in field and "max" in field and field["min"] > field["max"]:
                raise GeneratedUIContractError("generated UI numeric min exceeds max")
        elif raw.get("min") is not None or raw.get("max") is not None:
            raise GeneratedUIContractError("numeric bounds are allowed only for number fields")
        normalized.append(field)
    result: dict[str, Any] = {
        "schema_version": 1,
        "title": title,
        "fields": normalized,
        "submit_label": submit_label,
    }
    if description:
        result["description"] = description
    if confirmation_text:
        result["confirmation_text"] = confirmation_text
    return result
