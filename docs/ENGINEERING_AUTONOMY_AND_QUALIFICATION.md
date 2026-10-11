# Vishnu Engineering Autonomy and Qualification

Status: implemented on PR #142; acceptance remains bound to exact-head CI and review evidence.

## Purpose

Vishnu can turn an explicitly scoped Canonical WorkOrder into an isolated software-engineering candidate using governed model intelligence, repository editing, verification, repair, browser/device qualification, evidence, and independent final review. This subsystem does not create a second Work authority and does not replace the existing evolution, approval, security, recovery, continuity, model-routing, or release systems.

The implemented loop is:

`User request -> Canonical Work -> EngineeringSpec -> repository intelligence/impact -> governed model plan -> isolated worktree -> typed source edits -> local commit -> trusted verification -> bounded repair -> VERIFYING candidate -> browser/device/visual/accessibility/performance evidence -> trusted final qualification -> independent review -> qualified candidate -> separate owner/release authority`

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
| Auto-Fix | Yes | Yes | Yes, bounded | Final review after evidence |
| Review Candidate | Yes | Yes | Yes, bounded | Final review after evidence |

Starting the full end-to-end engineering action remains a critical owner-gated tool with fresh verification/reauthentication. Canonical Work repository/path scope is required before any workspace is prepared. Runtime and tool boundaries both enforce the selected mode.

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

## Canonical Work projection is monotonic

Engineering overrides cannot weaken the authoritative Work contract. Projection preserves or strengthens:

- the Canonical Work objective and requirements;
- success criteria;
- required tests;
- required states and reference designs;
- API/schema impacts;
- browser coverage;
- UI/accessibility/visual qualification requirements;
- independent review requirements;
- security classification;
- prohibited paths.

Path overrides may narrow a concrete Canonical Work scope, including to a true subdirectory. They cannot add a sibling or unrelated path. Arbitrary glob-subset claims fail closed when the relationship cannot be proven safely.

## Repository editing

The model-visible repository surface is bound to `work_order_id + attempt_id`. It never accepts repository roots, local paths, remotes, shell commands, merge targets, or deployment targets.

Supported operations are bounded read/search/diff/status plus guarded create/replace/exact-replace/delete/rename/restore. Mutations use SHA-256 stale-write preconditions, workspace confinement, symlink refusal, UTF-8-only rules, atomic replacement, path policy, protected-code policy, changed-file limits, per-file limits, and aggregate write-byte budgets.

Delete consumes the changed-file budget. Rename is treated as a governed text mutation: binary/NUL, invalid UTF-8, oversized sources, changed-file limits, and aggregate byte limits all fail closed.

The end-to-end planner itself emits only `replace_exact`, `create`, `delete`, and `rename` operations. It cannot emit commands.

## Model governance and budgets

Engineering planning and independent review use typed `ModelRequest` when the governed Intelligence Fabric is available. Requests are bound to the same Canonical WorkOrder and attempt, retain sensitive routing, carry `model_output_authority=false`, and use the owner per-Work model cost ceiling through the existing hierarchical BudgetEngine. Test doubles may use the simpler JSON protocol without becoming production authority.

## Repository intelligence and impact

The engineering code graph is revision-bound and reconstructable. It indexes source files/symbols/import relationships/routes and is used for deterministic impact analysis. It is a cache, not identity or authority state. Plain directory scopes and governed glob scopes use compatible inclusion semantics, so valid glob-scoped Work does not silently produce an empty graph.

Impact analysis identifies dependent files, relevant tests, UI/API/database/mobile/CI surfaces, authority-sensitive risk, responsive risk, and contract risk. Visual defects can be correlated with DOM/component/source evidence to rank likely UI source files.

## Local verification and bounded repair

When trusted local verification is enabled, model output never chooses commands. Vishnu runs a fixed no-shell verification sequence:

1. compile the governed repository code surfaces;
2. run the existing evolution/security safety suite;
3. run the full repository pytest suite.

Protected-code and Body-manifest checks run before candidate code execution through the existing guarded verification provider. Failed verification can enter the bounded repair loop up to the EngineeringSpec/owner limit. Interrupted verification marks Canonical Work recovery-required and preserves the candidate workspace/evidence.

A local candidate that passes these checks is still not a release and normally remains `VERIFYING` until its remaining evidence gates are supplied.

## Qualification gates are evidence-first

Required gates are explicit and missing evidence is `PENDING`, which blocks qualification. A boolean pass without an evidence reference is also `PENDING`; there is no evidence-free `PASS` path.

Core gates include:

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
- localization/content stress for UI Work;
- living Vishnu/3D behavior for UI Work;
- physical-device evidence for UI Work;
- deployed-preview evidence.

A `WARN` does not hide a `FAIL` or `PENDING`. Independent review cannot convert missing gate evidence into a pass.

## Trusted final qualification

Local engineering no longer asks the independent reviewer to approve a half-qualified candidate. Review is deferred while any required gate is missing or failing.

`EngineeringCandidateFinalizer` is a read-only second stage for an already committed candidate. It:

- requires a successfully completed local engineering attempt;
- reloads the persisted EngineeringSpec from the registered Work/Attempt workspace;
- requires a clean workspace at the exact durable candidate revision;
- reloads revision-bound local verification observations from attempt metadata;
- rejects external `requirements` gate claims and instead reconstructs that gate from exact `RequirementTrace` evidence;
- rejects any passing external observation without evidence;
- rejects external evidence not bound to the exact candidate revision;
- merges local and external observations fail-closed;
- keeps independent review deferred until every required gate is non-blocking;
- reruns independent review over the exact candidate diff and complete evidence set;
- emits `engineering.candidate.qualified`, review-rejected, or final-qualification-pending Work events;
- never edits, commits, pushes, merges, deploys, rolls back, approves owner actions, or activates a Body revision.

Owner Controls projects these final Work events so live engineering status does not remain stuck on stale local-attempt metadata.

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

Browser qualification payloads can carry `candidate_revision`; the adapter copies that binding into each generated observation so the trusted finalizer can reject cross-revision evidence.

## Visual qualification

Approved visual baselines are versioned by screen/browser/device/theme/state/reference version. Deterministic image diff runs first. Semantic visual review uses the existing `vision/screen_understanding.py` sanitized-evidence guard rather than a new screenshot trust model.

Visual defects are structured and can be correlated with DOM/component/source evidence before bounded repair. Raw private screenshots do not become shared training data by default.

## Database and API qualification

SQLite migration qualification runs trusted migration callbacks only against temporary database clones. Source databases are checked for symlinks before canonical resolution, opened read-only for backup, and hashed before/after; integrity, foreign-key constraints, and required tables are checked on the clone. Model-generated SQL is not accepted by the sandbox.

API contract qualification validates observed status codes and required/forbidden JSON keys. It does not send external requests itself; trusted API/browser runners provide observations.

## Dependency and supply-chain checks

Offline dependency qualification inspects supported manifests for direct VCS/URL/editable sources, unversioned dependencies, version ranges, lockfile transport, and integrity metadata. It does not contact package registries or mutate dependencies.

## Failure and flaky-test intelligence

Failure history stores sanitized normalized fingerprints. Secret-bearing excerpts are redacted before persistence. Repeated failures may require a permanent regression test. Flaky-test detection may identify instability but has no authority to suppress or auto-pass a gate.

## Requirement and user-flow traceability

Completion can be projected as an exact matrix from EngineeringSpec requirement/success-criterion text to evidence references and pass state. User-flow expectations use ordered steps plus evidence references. A candidate cannot become objectively complete merely because tests exist; required behavior must be traceable to evidence.

## Preview and production qualification

The environment observer is GET-only, explicitly host/origin allowlisted, redirect-disabled, response-size bounded, latency bounded, and does not embed credentials. An empty host allowlist is rejected. It can inspect a separately created preview or production origin and return evidence. It cannot create, promote, or delete deployments.

Production smoke regressions can be converted idempotently into Canonical Work for diagnosis. Automatically generated production-regression Work has no repository/path scope and no automatic mutation/deploy authority. A normal governed planning step must create separately scoped repair Work before code can change.

## Canary and rollback intelligence

Canary comparison can evaluate error rate, relative error increase, p95 latency, sample sufficiency, and additional checks. It can recommend rollback. It has `automatic_rollback_authority=false`; actual rollback remains a release/owner action.

## Evidence storage and portability

Engineering evidence uses append-only local JSONL outside candidate worktrees, no-follow opens, restricted permissions, and explicit symlink rejection before path resolution.

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

The existing Owner Controls Permissions surface receives an Engineering Autonomy panel. It shows policy controls plus recent WorkOrder, attempt, workspace, branch/candidate revision, repair count, final qualification state, and reviewer decision. Policy changes and starting full engineering Work require trusted owner context/fresh verification.

API tests verify trusted-admin access, fresh owner verification, mode gating, explicitly scoped Work execution, and absence of merge/deploy action controls.

## CI qualification behavior

CI, package, reliability/security, P3 iPhone PWA, and PWA visual qualification use per-workflow/per-event concurrency groups with `cancel-in-progress: true`. Superseded PR-head runs no longer need to consume hosted runner capacity once the new workflow revision is active.

## Definition of an engineering candidate

A local candidate commit is not a release. A candidate may be marked qualified only when every required gate has evidence, all blocking gates are clear, exact requirement traces pass, and the required independent review approves the exact candidate revision. Even then, merge/deployment/body activation are separate authorities.

## Current release rule

PR #142 must only be considered accepted when the exact final head has passed its authoritative repository workflows. Earlier green runs on superseded SHAs do not qualify the current candidate.
