# Governed Release & Production Autonomy

## Purpose

Vishnu's engineering subsystem may understand work, modify code in an isolated workspace, verify it, obtain independent review, and produce an exact qualified candidate. It does **not** own production release authority.

Governed Release & Production Autonomy is the separate authority domain that may move an exact qualified candidate through pre-production qualification and production under explicit owner policy.

The intended pipeline is:

`Canonical Work -> EngineeringSpec -> isolated engineering candidate -> exact qualification -> release handoff -> provider staging/preview -> read-only qualification -> production promotion -> production smoke -> canary/monitoring -> regression -> Canonical Work`

A rollback recommendation is not rollback authority. A Body/evolution activation is not release authority. Those boundaries remain separate.

## Non-negotiable authority boundaries

Release control never accepts an arbitrary repository/SHA pair from an owner API or a model. A ReleasePlan originates only from the trusted engineering finalizer after the exact candidate has passed its required gates and independent review.

The controller binds:

- Canonical WorkOrder and Attempt
- EngineeringSpec
- repository and base revision
- exact candidate revision
- SHA-256 digest of the trusted QualificationReport
- provider and logical target
- risk class and affected surfaces
- immutable release evidence

The model layer cannot read provider tokens, choose arbitrary deployment roots, execute shell commands, silently promote an unqualified candidate, grant its own approval, execute production rollback, or activate a Vishnu Body revision.

## Owner modes

Owner Controls exposes four release modes:

- **Off** — no preview/staging or production release authority.
- **Preview only** — qualified candidates may enter the provider's pre-production qualification gate but not be promoted.
- **Approval required** — production promotion requires owner approval.
- **Auto low-risk** — only releases classified **Low** may auto-promote, and only when they do not touch sensitive surfaces.

Automatic production is permanently capped at Low risk. It cannot be broadened to Medium, High, or Critical by configuration.

Sensitive surfaces always require owner approval. The protected markers include authentication, authorization, security, permissions, billing, payment, database/migrations, credentials/secrets, provider configuration, owner controls, release/deploy/runtime, Body, and evolution surfaces.

Rollback remains independently governed. Even when rollback execution is enabled in policy, the release must already be `rollback_recommended` and the owner action must explicitly confirm rollback.

## Release state machine

Core states are:

`planned -> previewing -> preview_qualifying -> preview_qualified -> promoting -> production_qualifying -> monitoring -> succeeded`

The generic `preview*` states mean the pre-production qualification gate. A provider may implement that gate with a true Preview environment or, when required for exact-artifact safety, a staged Production-target deployment that has not received production traffic.

Failure/safety states include:

- `awaiting_approval`
- `rollback_recommended`
- `rolling_back`
- `rolled_back`
- `recovery_required`
- `failed`
- `cancelled`

`recovery_required` is deliberately fail-closed. If Vishnu restarts after an authority-bearing provider action and cannot prove whether that action completed, it does not replay the action.

If a persisted provider deployment ID is available, restart recovery may only observe that deployment and rerun read-only qualification. Unknown preview/staging/promotion/rollback outcomes require owner/provider reconciliation.

## Pre-production qualification

Pre-production qualification is credential-free and GET-only. It:

- requires HTTPS
- rejects credentials, query strings, fragments, non-standard ports, and redirects
- limits requests to exact allowlisted hosts or explicitly configured DNS suffixes
- applies bounded response sizes and timeouts
- records trusted evidence against the exact candidate revision

A missing required qualification blocks production promotion.

## Production smoke and feedback

After production promotion, Vishnu performs the configured read-only production smoke qualification. A failed smoke check:

1. records production smoke evidence,
2. marks the release `rollback_recommended`, and
3. sends a high-severity `ProductionRegression` through the existing idempotent `ProductionRegressionWorkBridge` so Canonical Work receives the production problem.

This feedback path creates diagnosis Work only. It does not silently mutate code or grant rollback authority.

## Canary and continuous monitoring

Canary evaluation compares baseline and candidate metrics using owner policy thresholds for:

- minimum sample count
- absolute/increased error rate
- p95 latency ratio
- additional required checks

Insufficient evidence keeps the release in monitoring. Healthy evidence may complete the release. Regressive evidence recommends rollback and creates Canonical Work.

`ProductionReleaseMonitor` is read-only. It verifies the exact recorded production deployment and may rerun production smoke checks. Transient provider/network errors are recorded but do not immediately trigger rollback. Repeated failures reach the configured threshold, recommend rollback, and create production-regression Work.

The monitor has a bounded observation budget and configured polling interval.

## Render provider

Render release authority requires all of:

```text
VISHNU_RELEASE_RENDER_API_TOKEN
VISHNU_RELEASE_RENDER_PREVIEW_SERVICE_ID
VISHNU_RELEASE_RENDER_PRODUCTION_SERVICE_ID
VISHNU_RELEASE_RENDER_PREVIEW_URL
VISHNU_RELEASE_RENDER_PRODUCTION_URL
```

Preview and production must be distinct services.

Before every authority-bearing deployment, Vishnu reads the Render service configuration and refuses governed release unless provider auto-deploy is explicitly disabled/manual. This prevents an unrelated branch push from replacing the exact revision that Vishnu qualified.

Vishnu requests the exact commit revision, polls the provider until the deployment is live, and rejects revision drift. Rollback deploys the bound base revision only after separate rollback policy and owner confirmation are satisfied.

## Vercel provider

Vercel release authority requires:

```text
VISHNU_RELEASE_VERCEL_API_TOKEN
VISHNU_RELEASE_VERCEL_PROJECT_ID
VISHNU_RELEASE_VERCEL_PROJECT_NAME
VISHNU_RELEASE_VERCEL_GITHUB_ORG
VISHNU_RELEASE_VERCEL_GITHUB_REPO
VISHNU_RELEASE_VERCEL_PRODUCTION_URL
```

Optional scope values are:

```text
VISHNU_RELEASE_VERCEL_TEAM_ID
VISHNU_RELEASE_VERCEL_GIT_REF=main
VISHNU_RELEASE_VERCEL_PREVIEW_HOST_SUFFIX=.vercel.app
```

Vercel is deliberately different from Render. Vishnu does **not** qualify a Preview-environment artifact and then assume it can be promoted unchanged. Instead it:

1. reads `GET /v9/projects/{idOrName}` and requires `autoAssignCustomDomains=false`, failing closed if the setting is true, missing, or the project identity drifts;
2. creates the exact qualified Git SHA with `target=production`, producing a staged Production build that uses Production-scoped build/runtime configuration but does not receive the project's production domains;
3. waits for READY and proves both the exact candidate SHA and `target=production` from the deployment itself;
4. runs the generic pre-production qualification against that immutable deployment URL;
5. at promotion time, re-inspects the persisted deployment and again requires the exact SHA and `target=production`, preventing an older Preview-environment artifact from being promoted after a restart/upgrade;
6. promotes that same deployment so production traffic changes without a second build.

Rollback searches Production-target deployment history for an immutable deployment that proves the bound base revision, re-inspects it, proves `target=production` again, and only then requests traffic rollback after separate rollback authorization.

## Provider configuration rules

Leaving all provider fields blank keeps production deployment authority disabled while the rest of Vishnu remains operational.

A partially configured provider fails closed. Provider API tokens remain inside provider objects and protected environment/secret stores; they are excluded from dataclass representations, ReleasePlan, ReleaseEvidence, model context, owner API responses, and normal event payloads.

When exactly one provider is configured, it may be selected unambiguously. When multiple providers are configured, `VISHNU_RELEASE_DEFAULT_PROVIDER` must identify the intended provider before automatic handoff can execute.

## Owner Controls

The trusted Owner Controls surface provides:

- release policy/status summary
- release ledger/detail
- approve
- preview/staging + qualification
- production promote
- canary observation
- production regression signal
- explicit rollback
- cancel

Mutation and production actions require an active trusted admin device and fresh owner verification when PWA sessions are active.

There is intentionally no route that accepts an arbitrary candidate SHA to create a ReleasePlan.

## Runtime startup and recovery

The cloud runtime initializes release control independently. Missing/invalid provider configuration disables release authority without preventing Vishnu's broader runtime from starting.

At startup, release automation reconciles durable release state. Known deployments may be re-observed and read-only qualified. Uncertain authority-bearing actions move to `recovery_required` and are never replayed automatically.

A production monitoring worker observes releases already in `monitoring`; it does not create deployments or execute rollback.

## Qualification

`.github/workflows/release-autonomy.yml` is the focused authoritative release-control workflow. It compiles the release surfaces, runs controller/policy/provider/runtime/recovery/monitoring/feedback/Owner Controls tests, and asserts critical authority invariants.

The normal repository CI, Security/Reliability, P3 iPhone PWA, package validation, and relevant responsive/browser workflows remain required where triggered. A superseded SHA does not qualify the tranche.

The release definition is therefore:

**exact engineering candidate qualified -> governed release evidence complete -> owner policy satisfied -> exact provider staging/preview qualified -> exact production promotion proven -> smoke/canary/monitoring healthy -> no unresolved recovery/rollback state**.
