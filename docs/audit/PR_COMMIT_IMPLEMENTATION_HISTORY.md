# PR and Commit Implementation History

Baseline: `main` = `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

## Method and claim boundary

All 240 pull-request records were indexed and reconciled against the current `main` history. Git commit history was paginated through its terminal page; the connector proves more than 2,400 reachable commits and fewer than 2,501, but did not expose a reliable aggregate count, so the exact reachable-commit total is intentionally recorded as `NOT VERIFIED` rather than guessed.

This ledger does **not** claim a manual line-by-line reading of every historical diff. PR metadata/history is used as the change-set index; current-source inspection, selected PR changed-file sets/diffs, current CI, and exact-SHA source are used to decide present implementation truth. Closed/superseded drafts are not counted as live features merely because code once appeared in them.

GitHub issue numbers `#109`, `#153`, `#157`, `#159`, and `#160` are not PRs; this explains why PR numbering reaches #245 while the PR count is 240.

## Implementation ledger

| PR | Current interpretation |
|---|---|
| #1 | Native PyQt desktop UI foundation. |
| #2 | Removed legacy HTTP UI path and upgraded desktop product shell. |
| #3-#10 | v0.3/v1 API compatibility, validation and error-semantics hardening. |
| #11 | Dashboard API and pairing foundations. |
| #12-#15 | Trainer snapshot/validation and durable safe-refusal/progress correctness. |
| #16-#17 | Mobile notification hooks plus proactive dashboard/preferences. |
| #18-#19 | Computer-control engine/dashboard API and continuity dashboard. |
| #20-#23 | Global LLM concurrency, memory index, durable long tool calls, idempotent retry, scheduled/cron automation. |
| #24-#30 | Agent planning/goals, file intelligence, grounded datasets/evals, verified computer control, Intelligence Lab continuous improvement. |
| #31-#44 | Concurrent/cancellable agents and advanced candidate/speculation/reasoning controls including contradiction penalties, budgets, routing, synthesis and cancellation. |
| #45-#53 | Response-depth/body-size controls and complete Activities feed evolution: filtering, actors/sources, timestamps, snapshots and cursor pagination. |
| #54-#66 | Advanced reasoning core -> workflow/conversation integration -> metrics/reset -> desktop/config persistence -> adaptive policy/versioned replanning. |
| #67 | Playbooks/capability qualification. |
| #68-#79 | Projects/WorkPlan/live Work, replanning, Projects UI, status/activity propagation, global awareness, Attention Center, approval binding, recovery context, evidence/review, notifications/deep links and canonical Work state. |
| #80-#96 | Qualified planning, claim gates, Completion Judge, autonomy modes/UI, Work knowledge via Memory, WorkOrder detail, unified attention/events, restart/isolation tests, consistency/performance/qualification/release gates and whole-product release integrity. |
| #97 | Draft CL4R1T4S planner/integration map; superseded/not counted as current implementation authority. |
| #98 | Draft typed tool I/O hooks; superseded/not counted as current implementation authority. |
| #99-#102 | Persistent-agent Body/private Self, attempts/leases/recovery lineage, Evidence/unknown-outcome recovery, evidence ingestion/lifecycle/redaction/cursors. |
| #103-#104 | Stale duplicate E5/E6 drafts; not counted separately. |
| #105-#108 | Evidence-backed evolution, owner-approved immutable Work handoff, isolated code-body adoption, fenced cross-host agent continuity. |
| #110 | Audit/E9 planning and gap discovery; identified earlier E1/E2/E4/E5 and unlanded #97/#98 gaps. |
| #111 | E9 persistent-agent architecture end-to-end work. |
| #112-#113 | Intelligence Fabric drafts later superseded. |
| #114 | Consolidated Intelligence Fabric + Agent Workforce. |
| #115 | Agents UI parity work. |
| #116 | Visualize workspace + visual intelligence. |
| #117-#120 | Adaptive intelligence modes, governed training/Owner Controls, AUTO mode, governed self-improvement and qualification. |
| #121-#124 | Governed trained-model runtime/real ML canary, model artifact/release pipeline, portable intelligence manifest, restore preflight. |
| #125 | Superseded by #128. |
| #126 | Host-independent disaster recovery. |
| #127 | Superseded by #130. |
| #128-#130 | Manifest-bound continuity handoff, hardware profile/offline readiness, durable Intelligence Vault. |
| #131 | Duplicate/closed; no distinct live authority. |
| #132 | Multi-user contribution learning. |
| #133-#136 | Draft work superseded by #137-#140. |
| #137-#140 | Verified offline packs, fresh-machine activation gate, governed remote GPU training, specialist adapters. |
| #141 | Portable intelligence runtime + owner controls. |
| #142 | Governed engineering autonomy/code execution/qualification. |
| #143 | Governed release/production autonomy boundaries. |
| #144 | Qualification evidence gap closure. |
| #145 | Physical-device dispatch line later reconciled/closed; do not treat old state as final physical L4 proof. |
| #146 | Exact-revision physical-device qualification handoff. |
| #147 | Provider-backed production telemetry. |
| #148 | Owner Release monitoring. |
| #149 | Mobile preview Home race fix. |
| #150-#151 | Our Products foundation plus build lifecycle/numbering. |
| #152/#154 | Superseded by #155. |
| #155 | Complete Our Products integration: manifest/runtime, AI modes, signed `.vishnu-product`, Ed25519 signing, licenses, owner APIs, PWA/desktop UI; native production artifacts remained outside that PR's proof. |
| #156 | Stale overlap closed; no separate authority. |
| #158 | Verified Web/PWA/API/Worker runtime artifacts. |
| #161 | Governed platform runner + Android APK compiler. |
| #162 | Multi-platform development compilers/artifacts for Android/iOS/Windows/macOS/Linux/Docker; production signing remains external. |
| #163 | Governed production-product qualification gate. |
| #164 | Product Composer reusable capability engine. |
| #165 | Universal Content Intelligence stages 1-4: PDF/DOCX/XLSX/PPTX/text/CSV/JSON/XML/HTML + local OCR + KnowledgeStore. |
| #166 | Layout/forms/tables plus EML/EPUB/RTF/YAML/source/INI/TOML/ICS/VCF/ZIP/TAR/GZIP, FTS5, projects and governed tools. |
| #167 | Local OCR/visual document intelligence. |
| #168 | Audio/video/subtitles via FFmpeg/whisper.cpp/faster-whisper boundaries. |
| #169 | Semantic entities/relations/contradictions/timelines. |
| #170 | Governed owned training/classifier/OCR/table infrastructure. |
| #171 | Resumable large uploads, content-addressed store and durable worker queue; bounded materialization. |
| #172-#176 | OCR research progression from isolated glyphs -> closed-vocab word/line/handwriting/layout/table -> open-vocab segmental OCR/HTR -> NumPy temporal CTC -> whitespace gate fix. These do not justify a foundation-model claim. |
| #177 | Real-world qualification gate + neural layout/table; explicitly kept `real_world_corpus_qualified=false`. |
| #178-#180 | Grounded DocumentGraph/Q&A, persisted production semantic runtime/index, qualification hotfix. |
| #181-#182 | Multimodal chart/diagram/equation/screenshot intelligence and V1 qualifier; real-world evidence remained bounded and `foundation_model=false`. |
| #183 | Universal Capabilities: OpenAPI + MCP discovery/catalog, governed execution, owner/native capability UI/session integration, credential/audit/rehydration tests. External OAuth/public-provider verification was not asserted. |
| #184 | Removed unsafe production native targets; Android/iOS capability sign-in fails closed without approved non-production configuration. |
| #185-#187 | Capability Forge V1-V3: self-created capabilities, write action plans/forms/schedules/improvement, provenance/OAuth/canary/readiness, native management. Side effects remain staged/approved/governed. |
| #188 | Virtual Device Lab/Sensorium simulated L1/L2. |
| #189 | Sensorium virtual + read-only physical observation boundary; no execution authority. |
| #190 | Hardware-free virtual fleet. |
| #191 | Android Emulator, iOS Simulator and Linux/Windows/macOS hosted-VM qualification; physical L4 explicitly deferred. |
| #192 | Desktop first-run. |
| #193 | Mobile QR pairing first launch. |
| #194 | Zero-config local TLS/mDNS/certificate pinning. |
| #195 | Local-first Data Plane policies: `device_only`, `progress_only`, `sync_everywhere`, `on_demand`; adapters/settings. |
| #196 | Encrypted lease-bound transport, DEK/KEK envelopes and rotation. |
| #197-#198 | Provider/relay/PWA recovery/storage continuation line; governed adapters and opaque relay. Provider-specific native gaps remain explicit rather than silently emulated. |
| #199 | Atomic one-time recovery/WebAuthn challenge use. |
| #200 | Crash-safe SecretVault root-key rotation. |
| #201 | Strict hosted/security-sensitive configuration validation. |
| #202 | Runtime failure observability. |
| #203 | Shared SQLite foundation + versioned DeviceRegistry migrations. |
| #204 | MemoryStore shared SQLite migration. |
| #205 | MemoryStore sensitive-data encryption. |
| #206 | Knowledge + Projects shared SQLite adoption. |
| #207 | Runtime composition boundaries. |
| #208 | Split owner Memory/Knowledge routes to preserve domain separation. |
| #209 | Ruff gate/fixes. |
| #210 | Strict mypy key/SQLite typing line. |
| #211 | Architecture invariants: no intelligence-owned ToolRegistry, RootKeyStore restrictions, Memory/Knowledge separation, single DeviceRegistry/Gateway. |
| #212-#218 | Dependency locks, CycloneDX SBOM, license compliance, reproducibility evidence, backup/portable DR, endurance/concurrency and fault injection. |
| #219 | Product stores shared SQLite. |
| #220 | Universal first-device onboarding across desktop/browser/Android/iOS plus optional headless Render bootstrap. Physical/live-provider qualification remains separate. |
| #221 | Markdown notes + portable Knowledge archive. |
| #222 | Readiness/licensing refresh; recorded production offline/no active verified deployment rather than manufacturing a production claim. |
| #223 | REA draft superseded. |
| #224 | Official REA 6.5.0 local MCP projected through ToolRegistry; 207 tools. |
| #225 | Proprietary LICENSE + SECURITY posture. |
| #226 | Exact-SHA Cybersecurity Assurance: internal control/red-team evidence, not third-party certification. |
| #227 | Privacy-governed Sensorium Vision: camera permission/session, sparse live vision, visual memory, native desktop/external HTTPS cameras, Vision+Voice/task assistance; biometric authority remains separate. |
| #228 | Sensorium 2: phone sensors, permissions, screen/audio/AR/OCR/wearables/Home Assistant observation boundary/world model; no physical L4 claim. |
| #229 | Sensorium 3: active perception, causal/scene/task models, demo/procedural memory, outcome simulator and action-observation feedback; action authority still separate. |
| #230 | Production trust/universal continuity hardening: readiness evidence, strict physical L4 boundary, recovery ceremonies, multi-device continuity, Work 2.0, memory intelligence, OAuth/local intelligence, Trust Center/Eval Lab. External evidence not fabricated. |
| #231-#235 | Intelligence Lab phases 1-4: default-off research, autonomy, scale/performance, governed distributed compute through core ToolRegistry/DeviceGateway, and real-world/adaptive qualification requiring live evidence. |
| #236 | OpenVoice governed conversion. |
| #237 | Voice Intelligence personas/Voice Director/UI with limited claims. |
| #238 | Voice provider runtime draft. |
| #239 | Isolated voice boundaries, default off. |
| #240 | Integrated governed voice runtime. |
| #241 | VoiceStudio external provider, default off/loopback-first; AGPL external-service boundary and SecretVault credential handling. |
| #242 | VoiceStudio MCP through Universal Capabilities rather than a parallel executor. |
| #243 | Voice Lab v1 + governed telephony; no real-provider/physical-acoustic claim. |
| #244 | Adaptive universal composer with local intent classification/routing into existing authorities; no second executor. |
| #245 | Governed universal storage fabric: resumable provider transfers, provider capabilities/health, multipart S3/R2/B2, ranges, segmented encryption, placement plans and replica health; no silent copy/repair. Merged as current `main`. |

## Major live implementation domains derived from the ledger

1. Desktop/PWA/native product shells and onboarding.
2. Versioned owner/device APIs and modular server routes.
3. ToolRegistry, policy gateway, ApprovalManager, SecretVault and audit/evidence.
4. DeviceRegistry/DeviceGateway, pairing, continuity and trusted-device scopes.
5. Conversation, model routing, advanced reasoning and adaptive composition.
6. Agents, Work, Projects, Attention, durable execution and recovery.
7. Memory, Knowledge, file/content intelligence and semantic retrieval.
8. Universal Content Intelligence and bounded OCR/media pipelines.
9. Apps/Tools, Universal Capabilities OpenAPI/MCP and Capability Forge.
10. Computer/browser control through governed execution.
11. Automation, proactive behavior, activities and notifications.
12. Products/Product Composer and governed multi-platform build qualification.
13. Local-first Data Plane, encrypted leases and universal storage fabric.
14. Sensorium, virtual device lab, vision/world models and physical-observation boundaries.
15. Voice/OpenVoice/VoiceStudio/Voice Lab/telephony provider boundaries.
16. Intelligence Lab/self-improvement/training/model artifact/vault/offline/DR systems.
17. Architecture/security/reproducibility/SBOM/release qualification gates.

## Items that must not be double-counted as live features

Superseded/duplicate historical PRs include #97, #98, #103, #104, #112, #113, #125, #127, #131, #133-#136, #152, #154, #156 and #223, plus any historical implementation subsequently replaced by canonical current authorities. Their existence is historical evidence, not additional product scope.

## Commit-history interpretation

The commit stream contains merge commits, implementation commits, tests, qualification repairs, documentation, refactors and build/release evidence. A raw commit count is therefore not a feature count. Product truth is derived by reconciling those commits into the live domains above and then checking current source/CI at the audited SHA.
