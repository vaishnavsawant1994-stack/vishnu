from __future__ import annotations

from server.cloud_app import app, runtime
from server.trained_model_runtime_api import trained_model_runtime_router
from training.local_runtime import attach_local_model_runtime


# Explicit release-environment attachment. The normal cloud_app entrypoint is
# unchanged; only this wrapper enables the trained-checkpoint runtime.
attach_local_model_runtime(runtime)
app.include_router(trained_model_runtime_router(runtime))
