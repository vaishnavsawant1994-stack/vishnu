from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ApiContractCase:
    name: str
    method: str
    path: str
    expected_statuses: tuple[int, ...] = (200,)
    required_json_keys: tuple[str, ...] = ()
    forbidden_json_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("API contract case name is required")
        method = self.method.upper()
        if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("unsupported API contract method")
        object.__setattr__(self, "method", method)
        if not self.path.startswith("/"):
            raise ValueError("API contract path must be absolute")
        if not self.expected_statuses or any(not 100 <= int(value) <= 599 for value in self.expected_statuses):
            raise ValueError("API contract expected statuses are invalid")


@dataclass(frozen=True)
class ApiContractObservation:
    case: str
    passed: bool
    status_code: int
    missing_keys: tuple[str, ...] = ()
    forbidden_keys_present: tuple[str, ...] = ()
    summary: str = ""


class ApiContractQualifier:
    """Validate observed API responses against typed expectations.

    The qualifier never sends requests itself, so model output cannot turn a
    contract check into external action. Existing trusted browser/API runners may
    feed their observed response status and decoded JSON here.
    """

    @staticmethod
    def qualify(case: ApiContractCase, *, status_code: int, json_body: Mapping[str, Any] | None = None) -> ApiContractObservation:
        body = dict(json_body or {})
        missing = tuple(key for key in case.required_json_keys if key not in body)
        forbidden = tuple(key for key in case.forbidden_json_keys if key in body)
        passed = int(status_code) in case.expected_statuses and not missing and not forbidden
        pieces = [f"status={int(status_code)}"]
        if missing:
            pieces.append("missing=" + ",".join(missing))
        if forbidden:
            pieces.append("forbidden=" + ",".join(forbidden))
        return ApiContractObservation(case.name, passed, int(status_code), missing, forbidden, "; ".join(pieces))

    @classmethod
    def aggregate(cls, observations: Iterable[ApiContractObservation]) -> dict[str, object]:
        rows = tuple(observations)
        return {
            "passed": bool(rows) and all(item.passed for item in rows),
            "cases": [
                {
                    "name": item.case,
                    "passed": item.passed,
                    "status_code": item.status_code,
                    "missing_keys": list(item.missing_keys),
                    "forbidden_keys_present": list(item.forbidden_keys_present),
                    "summary": item.summary,
                }
                for item in rows
            ],
        }
