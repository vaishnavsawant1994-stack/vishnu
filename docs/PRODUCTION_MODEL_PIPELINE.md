# Vishnu Production Model Pipeline

Phase 6 turns the existing governed training/runtime pieces into a fail-closed production release chain without creating a second approval authority.

## Authority chain

The release path remains:

1. Training Capture creates governed candidates.
2. Only privacy-safe, provenance-complete, quality-qualified and owner-approved candidates may enter an immutable source-isolated dataset snapshot.
3. The configured trainer performs real weight training.
4. `ArtifactPublishingTrainerBackend` publishes the checkpoint into a content-addressed immutable artifact store before the model is registered.
5. The existing comprehensive evaluator must pass the candidate.
6. The existing live shadow runtime compares the candidate against authoritative responses. Shadow output is non-authoritative.
7. The existing governance ledger may mark a sufficiently qualified model as a promotion candidate.
8. Only the canonical owner may approve promotion.
9. The authenticated release controller may request deployment.
10. `ArtifactVerifiedDeploymentBackend` verifies the exact immutable artifact and refuses production activation unless the artifact store is explicitly declared persistent.
11. The existing deployment controller proves that the exact approved checkpoint is running before activation is recorded.
12. Rollback remains a release-controller action to the known-good parent and must prove the exact rollback checkpoint is running.

No trainer, evaluator, shadow model, model output, pipeline controller or background scheduler can grant owner approval or silently activate a model.

## Immutable artifacts

`training/artifact_store.py` provides a filesystem content-addressed store. Each checkpoint is copied into:

`<artifact-store>/artifacts/<sha256-of-file-inventory>/`

The manifest records every relative file path, byte size and SHA-256. Symbolic links are rejected. Verification re-hashes the entire checkpoint and fails on mutation, missing files, added files, path escape or an unmanaged checkpoint.

Persistence is deliberately explicit. A local directory is **not** considered production durable merely because it exists.

Configure:

```text
VISHNU_MODEL_ARTIFACT_STORE_DIR=/durable/path/vishnu-model-artifacts
VISHNU_MODEL_ARTIFACT_STORE_PERSISTENT=true
```

Set `VISHNU_MODEL_ARTIFACT_STORE_PERSISTENT=true` only when the path is genuinely backed by durable storage. On an ephemeral Render filesystem it must remain false.

## Serving requirements

The trained-model release entrypoint remains:

```text
uvicorn server.cloud_model_runtime:app --host 0.0.0.0 --port $PORT
```

It attaches:

- the real local checkpoint runner;
- the live local-transformers shadow backend;
- the governed deployment backend;
- the production artifact publisher;
- the artifact-verified production deployment gate;
- production readiness reporting.

Production serving requires all of the following to be genuinely configured:

```text
VISHNU_LOCAL_TRAINED_MODEL_RUNTIME=true
VISHNU_TRAINED_MODEL_RUNTIME_PERSISTENT=true
VISHNU_MODEL_ARTIFACT_STORE_PERSISTENT=true
VISHNU_MODEL_ARTIFACT_STORE_DIR=<durable-volume-path>
VISHNU_TRAINED_MODEL_API_KEY=<independent-inference-secret>
VISHNU_MODEL_RELEASE_TOKEN=<independent-release-controller-secret>
```

The inference API key and release-controller token are intentionally separate. Never use the model itself as release authority.

## Readiness API

Safe status endpoints:

- `GET /trained-model/health`
- `GET /trained-model/qualification`
- `GET /trained-model/production`

`/trained-model/production` reports explicit blockers such as:

- base model not configured;
- artifact store not persistent;
- trained-model runtime not persistent;
- shadow backend unavailable;
- deployment backend unavailable;
- inference key missing;
- release token missing.

It reports only whether secrets are configured, never secret values.

## Release endpoints

Inference remains protected by `VISHNU_TRAINED_MODEL_API_KEY`:

- `GET /trained-model/v1/models`
- `POST /trained-model/v1/chat/completions`

Release actions remain protected independently by `VISHNU_MODEL_RELEASE_TOKEN`:

- `POST /trained-model/release/deploy/{model_id}`
- `POST /trained-model/release/rollback/{active_model_id}`

A valid release token cannot bypass owner promotion approval, immutable artifact verification, persistence requirements or exact-checkpoint proof.

## Qualification vs production

`scripts/qualify_model_runtime.py` is a synthetic infrastructure canary. It now proves:

- real bounded weight training;
- immutable content-addressed artifact publication;
- artifact integrity verification;
- reloadable inference from the immutable artifact;
- exact-checkpoint deployment through the artifact-verified backend;
- switch to a distinct exact candidate artifact;
- switch-back to a distinct known-good artifact.

The canary intentionally uses synthetic non-user data and an isolated test-harness persistence declaration. Therefore it does **not** prove:

- production-quality model behavior;
- production durable storage;
- owner promotion approval;
- production-controller rollback lineage;
- production activation.

Those claims may be made only after real owner-approved Vishnu data, held-out evaluation, live shadow evidence, owner approval and deployment on genuinely durable production infrastructure all pass.
