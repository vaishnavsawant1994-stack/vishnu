# Governed trained-model runtime

Vishnu's trained-model runtime is an explicit release-environment extension of the existing governed self-improvement stack. The normal `server.cloud_app:app` entrypoint remains unchanged. To attach local trained-checkpoint shadow serving and deployment, start `server.cloud_model_runtime:app` and set `VISHNU_LOCAL_TRAINED_MODEL_RUNTIME=true`.

## Safety and authority boundaries

The runtime does not approve a model, alter training eligibility, lower evaluation thresholds, grant tools, change provider credentials, merge code, or deploy itself. Live shadow observations remain non-authoritative. Deployment still passes through `ModelDeploymentController`, which requires an already owner-approved model and proves the exact checkpoint is running before activation is recorded.

By default, deployment on an ephemeral filesystem is unavailable. Set `VISHNU_TRAINED_MODEL_RUNTIME_PERSISTENT=true` only when `PERSONAL_AI_DATA_DIR` is backed by durable storage. `VISHNU_ALLOW_EPHEMERAL_MODEL_ACTIVATION=true` exists only for explicit development experiments and must not be treated as durable production deployment.

## Environment

- `VISHNU_LOCAL_TRAINED_MODEL_RUNTIME=true` — attach the local Transformers shadow/deployment backend.
- `VISHNU_TRAINED_MODEL_RUNTIME_PERSISTENT=true|false` — declares whether the runtime data directory survives process replacement.
- `VISHNU_ALLOW_EPHEMERAL_MODEL_ACTIVATION=true|false` — explicit development-only override; default false.
- `VISHNU_TRAINED_MODEL_API_KEY` — bearer credential for the OpenAI-compatible trained-model inference endpoint.
- `VISHNU_MODEL_RELEASE_TOKEN` — separate bearer credential for release-controller deploy/rollback endpoints. Possessing this token does not bypass owner promotion approval.
- `PERSONAL_AI_DATA_DIR` — storage root for checkpoints, lineage, runtime pointer and qualification evidence.

Install optional ML dependencies with `pip install -r requirements-ml.txt`.

## Real ML runtime qualification

Run:

```bash
python scripts/qualify_model_runtime.py
```

The qualification uses synthetic non-user records and defaults to `hf-internal-testing/tiny-random-gpt2`. It performs real full-weight training with bounded settings, writes a checkpoint, reloads the checkpoint, and runs an inference probe. Evidence is written to `PERSONAL_AI_DATA_DIR/model-runtime-qualification/qualification.json` and is also available at `/trained-model/qualification` when the wrapper app is running.

This qualification proves the ML stack and checkpoint-serving path work. It intentionally does **not** run owner promotion, does not claim model quality, and does not activate the canary.

## HTTP surfaces

- `GET /trained-model/health` — safe runtime/backend status.
- `GET /trained-model/qualification` — synthetic ML runtime qualification evidence.
- `GET /trained-model/v1/models` — bearer-authenticated active trained model listing.
- `POST /trained-model/v1/chat/completions` — bearer-authenticated active-model inference.
- `POST /trained-model/release/deploy/{model_id}` — release-token protected; existing owner approval and exact-checkpoint gates still apply.
- `POST /trained-model/release/rollback/{active_model_id}` — release-token protected rollback to the governed known-good parent.
