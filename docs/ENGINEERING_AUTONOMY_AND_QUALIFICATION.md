# Vishnu Engineering Autonomy and Qualification

Status: implemented on PR #142; acceptance remains bound to exact-head CI and review evidence.

## Purpose

Vishnu can turn an explicitly scoped Canonical WorkOrder into an isolated software-engineering candidate using governed model intelligence, repository editing, verification, repair, review, browser/device qualification, and evidence. This subsystem does not create a second Work authority and does not replace the existing evolution, approval, security, recovery, continuity, model-routing, or release systems.

The target loop is:

`User request -> Canonical Work -> EngineeringSpec -> repository intelligence/impact -> governed model plan -> isolated worktree -> typed source edits -> local commit -> trusted verification -> bounded repair -> browser/device/visual/accessibility/performance qualification -> independent review -> candidate evidence -> separate owner/release authority`

## Non-negotiable authority boundary

Engineering Autonomy has no method that can silently:

- push a Git remote;
- merge a pull request;
- deploy or publish a release;
- perform production rollback;
- activate a Vishnu Body revision;
- modify owner approval/security policy to approve itself;
- obtain a generic shell or arbitrary filesystem root from a model.

Self-evolution remains under the existing `evolution/` authority. Normal engineering uses `future_intelligence/engineering/` and Canonical Work.

## Engineering Autonomy modes

Owner Controls exposes five durable modes:

| Mode | Read/analyze | Isolated source mutation | Bounded auto repair | Candidate review |
| --- | --- | --- | --- | --- |
| Off | policy-disabled for automatic engineering | No | No | No |
| Analyze | Yes | No | No | No |
| Workspace | Yes | Yes, active scoped Work/Attempt only | No automatic full loop | Optional/external |
| Auto-Fix | Yes | Yes | Yes, bounded | Required when EngineeringSpec requires it |
| Review Candidate | Yes | Yes | Yes, bounded | Yes |

Starting the full end-to-end engineering action remains a critical owner-gated tool with fresh verification/reauthentication. Canonical Work repository/path scope is required before any workspace is prepared.

## Owner policy

The durable local Engineering Autonomy policy controls:

- maximum changed files;
- maximum file and aggregate bytes;
- maximum repair cycles;
- browser qualification depth;
- visual qualification level;
- preview observation permission;
- ordinary/sensitive/authority security ceiling;
- evidence retention preference;
- per-Work model cost ceiling;
- physical-device requirement for UI Work;
- performance qualification;
- localization/content-stress qualification for UI Work;
- living Vishnu/3D qualification for UI Work.

The policy can narrow a Canonical Work EngineeringSpec. It cannot broaden the WorkOrder's authorized repository/path scope or turn protected/authority paths into ordinary paths.

## Repository editing

The model-visible repository surface is bound to `work_order_id + attempt_id`. It never accepts repository roots, local paths, remotes, shell commands, merge targets, or deployment targets.

Supported operations are bounded read/search/diff/status plus guarded create/replace/exact-replace/delete/rename/restore. Mutations use SHA-256 stale-write preconditions, workspace confinement, symlink refusal, UTF-8-only rules, atomic replacement, path policy, protected-code policy, and file/byte budgets.

The end-to-end planner itself emits only `replace_exact`, `create`, `delete`, and `rename` operations. It cannot emit commands.

## Model governance and budgets

Engineering planning and independent review use typed `ModelRequest` when the governed Intelligence Fabric is available. Requests are bound to the same Canonical WorkOrder and attempt, retain sensitive routing, carry `model_output_authority=false`, and use the owner per-Work model cost ceiling through the existing hierarchical BudgetEngine. Test doubles may use the simpler JSON protocol without becoming production authority.

## Repository intelligence and impact

The engineering code graph is revision-bound and reconstructable. It indexes source files/symbols/import relationships/routes and is used for deterministic impact analysis. It is a cache, not identity or authority state.

Impact analysis identifies dependent files, relevant tests, UI/API/database/mobile/CI surfaces, authority-sensitive risk, responsive risk, and contract risk. Visual defects can be correlated with DOM/source hints to rank likely UI source files.

## Qualification gates

Required gates are explicit and missing evidence is `PENDING`, which blocks qualification. Core gates include:

- requirements;
- build;
- unit;
- integration;
- security.

When relevant, qualification also requires:

- responsive layout;
- Chromium;
- WebKit;
- Firefox;
- runtime console/network behavior;
- approved visual baseline evidence;
- accessibility;
- performance;
- localization/content stress;
- living Vishnu/3D behavior;
- physical-device evidence;
- deployed-preview evidence.

A `WARN` does not hide a `FAIL` or `PENDING`. Independent review cannot convert missing gate evidence into a pass.

## Browser and responsive qualification

The shared browser qualification covers phone through large desktop widths and breakpoint-neighbour values. Existing Vishnu screen-specific browser tests remain in place. Engineering qualification adds:

- Chromium full compatibility lane;
- WebKit critical/mobile lane;
- Firefox critical lane;
- offline and reconnect checks;
- 401/403/404/500 state handling;
- long German text;
- emoji and multilingual Unicode;
- RTL stress;
- long URLs and no-break strings;
- text scaling;
- light/dark color-scheme propagation;
- reduced motion;
- mobile keyboard-like viewport shrink and orientation changes;
- safe-area/viewport containment;
- accessibility through Axe;
- performance safety budgets;
- WebGL-unavailable living-presence fallback.

## Visual qualification

Approved visual baselines are versioned by screen/browser/device/theme/state/reference version. Deterministic image diff runs first. Semantic visual review uses the existing `vision/screen_understanding.py` sanitized-evidence guard rather than a new screenshot trust model.

Visual defects are structured and can be correlated with DOM/component/source evidence before bounded repair. Raw private screenshots do not become shared training data by default.

## Database and API qualification

SQLite migration qualification runs trusted migration callbacks only against temporary database clones. Source databases are opened read-only for backup and hashed before/after; integrity, foreign-key constraints, and required tables are checked on the clone. Model-generated SQL is not accepted by the sandbox.

API contract qualification validates observed status codes and required/forbidden JSON keys. It does not send external requests itself; trusted API/browser runners provide observations.

## Dependency and supply-chain checks

Offline dependency qualification inspects supported manifests for direct VCS/URL/editable sources, unversioned dependencies, version ranges, lockfile transport, and integrity metadata. It does not contact package registries or mutate dependencies.

## Failure and flaky-test intelligence

Failure history stores sanitized normalized fingerprints. Secret-bearing excerpts are redacted before persistence. Repeated failures may require a permanent regression test. Flaky-test detection may identify instability but has no authority to suppress or auto-pass a gate.

## Requirement and user-flow traceability

Completion can be projected as an exact matrix from EngineeringSpec requirement/success-criterion text to evidence references and pass state. User-flow expectations use ordered steps plus evidence references. A candidate cannot become objectively complete merely because tests exist; required behavior must be traceable to evidence.

## Preview and production qualification

The environment observer is GET-only, host/origin bounded, redirect-disabled, response-size bounded, latency bounded, and does not embed credentials. It can inspect a separately created preview or production origin and return evidence. It cannot create, promote, or delete deployments.

Production smoke regressions can be converted idempotently into Canonical Work for diagnosis. Automatically generated production-regression Work has no repository/path scope and no automatic mutation/deploy authority. A normal governed planning step must create separately scoped repair Work before code can change.

## Canary and rollback intelligence

Canary comparison can evaluate error rate, relative error increase, p95 latency, sample sufficiency, and additional checks. It can recommend rollback. It has `automatic_rollback_authority=false`; actual rollback remains a release/owner action.

## Portability

Engineering artifacts are explicitly classified:

Portable:
- owner Engineering Autonomy policy;
- project instructions;
- approved design contracts;
- verified engineering lessons.

Rebuildable:
- repository/code graph;
- dependency index;
- worktrees;
- browser caches.

Sensitive evidence:
- screenshots;
- DOM snapshots;
- network payloads;
- database fixtures.

Unknown artifact kinds fail closed as sensitive evidence. Shared learning is disabled by default for all engineering artifact classes.

## Owner Controls live work view

The existing Owner Controls Permissions surface receives an Engineering Autonomy panel. It shows policy controls plus recent WorkOrder, attempt, workspace, branch/candidate revision, repair count, qualification state, and reviewer decision. Policy changes and starting full engineering Work require trusted owner context/fresh verification.

## Definition of an engineering candidate

A local candidate commit is not a release. A candidate may be marked qualified only when every required gate has non-blocking evidence and the required independent review is approved. Even then, merge/deployment/body activation are separate authorities.

## Current release rule

PR #142 must only be considered accepted when the exact final head has passed its authoritative repository workflows. Earlier green runs on superseded SHAs do not qualify the current candidate.
