from __future__ import annotations

from future_intelligence.engineering.release_qualification import (
    ProductionRegression,
    ProductionSmokeProvider,
)


class RegressionAwareProductionSmokeProvider:
    """Production smoke adapter that closes the production -> Canonical Work loop.

    The wrapped smoke provider remains read-only. A failed smoke result is
    converted into the existing idempotent ProductionRegressionWorkBridge input
    before the controller marks the release rollback-recommended. This adapter
    adds no deployment or rollback authority.
    """

    def __init__(self, inner: ProductionSmokeProvider, regression_bridge) -> None:
        self.inner = inner
        self.regression_bridge = regression_bridge

    def smoke_production(self, *, target: str, release_revision: str):
        result = self.inner.smoke_production(
            target=target,
            release_revision=release_revision,
        )
        if not result.passed and self.regression_bridge is not None:
            self.regression_bridge.create(
                ProductionRegression(
                    release_revision=release_revision,
                    target=target,
                    signal=result.summary or "production smoke qualification failed",
                    evidence=tuple(result.evidence),
                    severity="high",
                )
            )
        return result
