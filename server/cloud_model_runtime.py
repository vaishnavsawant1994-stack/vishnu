from __future__ import annotations

from server.cloud_app import app, runtime
from server.trained_model_runtime_api import trained_model_runtime_router
from training.local_runtime import attach_local_model_runtime
from training.production_pipeline import attach_production_model_pipeline


# Explicit release-environment attachment. The normal cloud_app entrypoint is
# unchanged; only this wrapper enables trained-checkpoint serving. Phase 6 adds
# immutable artifact publication and a fail-closed production release gate on
# top of the existing owner/shadow/deployment authority chain.
attach_local_model_runtime(runtime)
attach_production_model_pipeline(runtime)
app.include_router(trained_model_runtime_router(runtime))
