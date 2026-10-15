"""Expose the official REA runtime through Vishnu's governed ToolRegistry."""
from __future__ import annotations

from dataclasses import dataclass

from integrations.rea import REAMCPRuntime, REARegistration, register_rea_tools


@dataclass
class ReverseEngineeringCapability:
    runtime: REAMCPRuntime
    registration: REARegistration

    def close(self) -> None:
        self.runtime.close()


def register(registry, _settings) -> ReverseEngineeringCapability:
    runtime = REAMCPRuntime.from_environment()
    registration = register_rea_tools(registry, runtime)
    return ReverseEngineeringCapability(runtime=runtime, registration=registration)
