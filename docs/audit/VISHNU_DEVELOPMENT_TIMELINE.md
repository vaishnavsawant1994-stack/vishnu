# Vishnu Development Timeline

**Current audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Date:** 2026-10-17  
**Method:** feature lineage reconstructed from the exhaustive historical PR ledger and reachable-commit ledger generated at the PR #245 baseline, then reconciled through current PR #252 and current source/UI truth.

This is a chronological reconstruction of logical development phases. It deliberately does not count every PR as a separate feature.

## Phase 0 — Imported Personal AI foundation

### 2026-09-28 — PR #1

PR #1 imported the complete integration snapshot from the earlier `sawantvaishnav1994-ai/personal-ai` project into the new Vishnu repository. Merge: `c1cd8b7f2e507befb7f4cad37de6208d75a75a72`.

The repository therefore did **not** start as an empty application. Conversation, Memory/Knowledge foundations, owner/runtime code, desktop/PWA/mobile source, tools and supporting systems arrived as an imported baseline. Historical provenance before that import lives outside this repository.

## Phase 1 — Mobile/PWA product shell and early owner UI

### PRs #3–#29

The first major in-repository campaign concentrated on the mobile/PWA experience, neural Core presentation, Home, conversation layout, Conversations/Timeline/Today, owner controls, responsiveness, dialogs and broader surface polish.

Important lineage:
- #3–#6 established/polished the mobile conversation/Home shell.
- #7–#18 contain multiple stacked reference/draft iterations; many were closed or later absorbed rather than becoming separate canonical products.
- #19 became the main-bound integration path for approved UI work.
- #20–#29 repaired session gating, timezone behavior, dashboards, interaction details, movable dialogs, responsiveness and qualification.

Current relevance: these PRs explain the PWA’s unusually broad owner surface, but later UI truth work (#250/#251) is the canonical screen taxonomy.

## Phase 2 — Vishnu branding, Projects and daily owner work

### PRs approximately #35–#61

The product moved from the earlier Personal AI identity toward Vishnu, while Projects, project workspaces, Today, Conversations, Memory, Knowledge, Activities, Settings and richer owner navigation were built out.

Representative milestones:
- #35 — Vishnu naming/product identity transition.
- #46/#51 — Projects and project workspace foundations.
- #54/#56 — project activity/live work and broader Today/Conversation/Memory/Knowledge/Activity surfaces.
- #57 — Settings.
- #60 — Memory and owner-control refinement including richer Memory views.

This phase created much of the recognizable owner product shell that later campaigns connected to deeper orchestration/security authorities.

## Phase 3 — Canonical Work, evidence and governed autonomy

### PRs #62–#96

This is one of the most important architecture phases. Vishnu gained a canonical durable-work model instead of treating agent activity as ad-hoc prompts.

Lineage:
- #62 — GoalSpec/WorkPlan/WorkOrder/Evidence/Claim foundations.
- #63–#69 — runtime bridge, hierarchical planning/review, specialist/capability registries and safe replanning.
- #68–#72 — Projects integration, WorkPlan/Live Work UI and global work summaries.
- #73–#78 — Attention/Inbox, approval/recovery context, evidence/review context, notifications and deep links.
- #79–#86 — living state projection, qualification policies, domain claim gates, Completion Judge, autonomy modes and governed Memory promotion.
- #87–#93 — WorkOrder UX, Attention Center, event projection, crash/restart recovery, multi-project isolation, consistency and scale/performance.
- #94–#96 — whole-product qualification and release integrity.

Canonical result today: Work/Projects/Attention/Evidence remain distinct but connected through durable work authorities. Many focused tests exist, but the complete owner run→approve→cancel/recover→complete journey is still classified PARTIAL under strict E2E rules.

## Phase 4 — Persistent agents and Agent Workforce

### PRs #97–#115

The E-series work added persistent agent identity, leases/attempts, effect receipts, evidence ingestion, evolution/handoff/code-body review and cross-host continuity.

- #97/#98 were earlier planner/tool contracts.
- #99–#108 built durable identity/execution and cross-host continuity.
- #110 identified convergence gaps.
- #111 is the important E9 convergence point and supersedes narrower earlier contracts.
- #112–#115 expanded this into Intelligence Fabric / Agent Workforce, specialist teams, providers/budgets/failover and owner UI.

Current canonical implementation: persistent agent/work authorities plus Agent Workforce layers; older narrow E-series variants are historical lineage.

## Phase 5 — Adaptive intelligence, Visualize, training and model lifecycle

### PRs #116–#122

- #116 — Visualize/visual-intelligence workspace lineage.
- #117 — STANDARD/SMART/DEEP/RESEARCH modes.
- #118 — AUTO routing.
- #119–#120 — self-improvement/training capture governance.
- #121–#122 — trained-model runtime, qualification/canary and artifact/release pipeline.

Current status: adaptive routing is a product feature; self-improvement/training/model-promotion remains governed/experimental rather than unrestricted autonomous learning.

## Phase 6 — Portable Intelligence and governed engineering/release autonomy

### PRs #123–#149

This phase added portable/offline intelligence, manifests/preflight/disaster recovery, Intelligence Vault/privacy contribution concepts, packs, fresh-machine/remote-GPU/specialist adapters, and owner controls. Several stacked drafts were superseded by later canonical PRs rather than remaining parallel systems.

Later in the same phase:
- #142 — engineering autonomy/qualification boundaries, explicitly without blanket push/merge/deploy authority.
- #143 — governed release/production automation with preview/smoke/canary/rollback controls.
- #144–#148 — qualification evidence, provider telemetry and release monitoring.
- #149 — targeted Home/UI repair.

## Phase 7 — Our Products / Product Composer and cross-platform runners

### PRs #150–#164

Vishnu gained a product-composition subsystem: product definitions, lifecycle, signed `.vishnu-product` artifacts, licensing/distribution gates, deterministic Web/PWA/API/Worker outputs, platform runners/compiler targets and owner Product Composer surfaces.

Targets include desktop/server/container/mobile build paths. Current source is meaningful, but public distribution remains blocked by external signing/notarization/store acceptance and exact production acceptance. The current owner UI treats these as advanced/experimental product-building surfaces.

## Phase 8 — Universal Content Intelligence

### PRs #165–#182

This campaign expanded file/document understanding:
- document/layout/form/table parsing,
- OCR/handwriting lineage,
- audio/video/content extraction,
- graph/contradiction/timeline reasoning,
- grounded document understanding,
- semantic runtime and multimodal visual reasoning,
- model/real-world qualification contracts.

Canonical today: `file_intelligence/`, Knowledge ingestion and content APIs. Important boundary: synthetic/focused tests and optional model adapters are not blanket proof of real-world accuracy for every format or corpus.

## Phase 9 — Universal Capabilities, OpenAPI, MCP and Capability Forge

### PRs #183–#187

- #183 — Universal Capabilities: OpenAPI catalog/import, governed operations, credentials, risk/approvals, MCP discovery/execution, audit, restart rehydration and desktop/mobile management foundations.
- #184 — production-target repair and stricter mobile/provider boundaries.
- #185–#187 — Capability Forge V1→V2→V3 lineage; V3 is the latest advanced implementation.

Canonical authorities: `ToolRegistry`, `ApprovalManager`, `SecretVault`, capability catalog/service and audit. Forge does not replace those authorities.

External OAuth/provider configuration and arbitrary third-party acceptance remain separate from fixture qualification.

## Phase 10 — Sensorium Native Device Lab and device qualification

### PRs #188–#191

Vishnu added provider abstractions/evidence for Android Emulator, iOS Simulator and hosted Linux/Windows/macOS VMs, integrated with Sensorium/DeviceRegistry/DeviceGateway boundaries.

Key rule retained today: emulator/simulator/hosted-VM evidence is qualification level evidence, not physical-device L4 acceptance. No owner-facing adb/simctl/shell execution console is granted merely because the lab exists.

## Phase 11 — Universal first-device identity, local connectivity and local-first Data Plane

### PRs #192–#199

- #192 — desktop Create/Connect/Restore and owner setup foundations.
- #193 — mobile QR pairing.
- #194 — local TLS/mDNS/fingerprint connectivity.
- #195 — local-first Data Plane with the four policies `device_only`, `progress_only`, `sync_everywhere`, `on_demand`.
- #196 — encrypted lease-bound transport/key envelopes.
- #197 — provider/relay/PWA/offline/recovery qualification expansion.
- #199 — atomic credential/recovery-use hardening.

This established the core principle that data location is owner-controlled and cloud is optional.

## Phase 12 — Production hardening, SQLite consolidation and universal first-device creation

### PRs #200–#225

Security/data foundations were systematically hardened:
- #200 — crash-safe SecretVault root-key rotation.
- #201 — strict hosted/security-sensitive configuration validation.
- #202 — silent runtime failure observability.
- #203 — shared SQLite foundation and DeviceRegistry migrations.
- #204 — MemoryStore migrations.
- #205 — sensitive MemoryStore encrypted-at-rest lineage.
- #206 — Knowledge/Projects SQLite adoption.
- #207 — typed runtime composition boundaries.
- #208–#211 — route/module split, static quality, typing, architecture invariants.
- #212–#215 — locked dependencies, SBOM, licensing/reproducibility.
- #216–#219 — disaster recovery, endurance/concurrency, fault injection and remaining SQLite adoption.
- #220 — universal first-device creation/restore across platforms.
- #221 — Markdown/portable Knowledge archive lineage.
- #222 — production readiness/licensing reconciliation.
- #223 — first REA integration attempt, superseded.
- #224 — canonical REA 6.5.0 local stdio MCP integration.
- #225 — proprietary licensing/security-policy reconciliation.

Important canonical decisions: SQLite remains the production datastore; Memory and Knowledge remain separate; the repo/license is proprietary/all-rights-reserved; no later subsystem should create duplicate approval/device/tool/secret authorities.

## Phase 13 — Vision/Sensorium expansion and Intelligence Lab

### PRs #226–#235

- #226 — exact-SHA cybersecurity assurance program.
- #227 — governed Vision/Sensorium vision.
- #228 — context/world model, privacy zones, wearables/IoT/read-only Home Assistant and richer native sensing.
- #229 — causal world model, scene/task/procedure learning and simulator/action-observation research.
- #230 — production trust/continuity and wider runtime hardening.
- #231–#235 — Intelligence Lab phases: isolated opt-in research, higher autonomy research, scale/performance, governed distributed compute and adaptive qualification.

Current boundary: Sensorium has real product/privacy foundations plus experimental intelligence layers. Intelligence Lab remains isolated/experimental; physical actions remain policy/device gated.

## Phase 14 — Voice Intelligence, provider runtime, VoiceStudio and Voice Lab

### PRs #236–#243

- #236 — optional governed OpenVoice conversion.
- #237 — Voice Intelligence/personas/director/delivery/lexicon/multilingual plans/quality evaluation.
- #238 — earlier provider-runtime attempt.
- #239 — canonical optional provider runtime boundary, default-off until configured.
- #240 — queue/model/device/Sensorium integration.
- #241 — VoiceStudio external provider integration.
- #242 — VoiceStudio MCP tools governed through Universal Capabilities with narrow loopback exception.
- #243 — Voice Lab v1 and governed/default-off telephony.

Current boundary: voice has extensive source and fixture qualification, but real provider accounts, real microphones/speakers/acoustics and telephony acceptance remain configuration/external evidence.

## Phase 15 — Universal composer and Storage Fabric

### PRs #244–#245

- #244 — adaptive universal composer routing across chat/projects/memory/files/research/code/automation/devices/capabilities/visualization/voice.
- #245 — governed Universal Storage Fabric: resumable transfer, provider health, multipart/range support, segmented authenticated encryption reuse, placement planning and non-destructive reconciliation.

PR #245 merge `a8d3310b4d9090a42800621b1b27cb6045443c1e` became the baseline for the repository-wide forensic Product Truth audit.

## Phase 16 — Repository Product Truth reconstruction

### PR #246

PR #246 merged the source-derived Product Truth audit as `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`.

At its baseline it recorded:
- 58 top-level subsystem directories,
- 1,827 tracked files,
- 2,407 reachable commits,
- 240 PR records (204 merged, 36 closed-unmerged),
- 818 static API-style route declarations,
- 647 Python test modules,
- 33 domain-level truth records,
- a clean full-suite rerun of 3,840 tests after correcting an audit-container proxy condition.

PR #247 was a duplicate audit branch and intentionally closed unmerged after #246 made it redundant.

## Phase 17 — Canonical 63-screen UI truth and source-gap closure

### PRs #248–#251

- #248 — draft 29-screen/source audit + Web Companion overlap repair; closed unmerged.
- #249 — stacked draft 30-screen/Data & Storage/About work; closed unmerged.
- #250 — **merged canonical UI blueprint**, merge `1e6e89b64ca67c77c6189d37db8e581997af75f7`. It derived 63 logical owner screens, 57 source-present, 52 partial, 5 experimental, 6 missing and 0 strict complete.
- #251 — **merged source-gap completion**, current main merge `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`. It implemented all six missing source surfaces: Data Placement Policy, Setup Review, Storage Provider Detail, Sensorium Status, Updates & Release, and About/Notices.

Current canonical UI result: **63 source-present, 58 PARTIAL, 5 EXPERIMENTAL, 0 MISSING, 0 strict COMPLETE**. The older 29/30-screen taxonomies are superseded.

## Phase 18 — Open owner capability directory

### PR #252 — current open draft

Branch: `feat/owner-capabilities-directory`  
Head: `3358cd9b962db1b32b83dd9513e717fe3c8d910e`

Adds a searchable owner-facing PWA guide for capabilities, tools, specialists, labs and REA with explicit routing tests. It is **not on current main** and therefore is not counted as current product functionality.

Recommended action: continue the draft, reconcile its claims to this historical audit, run exact-head qualification, then merge only if the guide remains source-truthful.

## Current history totals

The PR #245 forensic baseline contained 2,407 reachable commits. Current main is exactly 52 commits ahead of that baseline, yielding **2,459 reachable commits** at the audited SHA.

Current PR totals at 2026-10-17:
- **247 PRs total**
- **207 merged**
- **39 closed without merge**
- **1 open draft (#252)**

The exhaustive pre-#246 PR details remain in `docs/audit/pr_implementation_ledger.md` / `.json`; every reachable pre-#246 commit remains in `docs/audit/commit_ledger.csv`. This timeline is the feature-level interpretation of those raw ledgers, not a replacement for them.