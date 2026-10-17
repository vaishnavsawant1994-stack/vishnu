# Vishnu PR → Feature Matrix

**Audited current main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Current PR totals:** 247 total / 207 merged / 39 closed-unmerged / 1 open draft.

## How this matrix is complete without duplicating the 240-row historical ledger

The repository already contains the exhaustive row-level PR record through the PR #245 baseline:

- `docs/audit/pr_implementation_ledger.md`
- `docs/audit/pr_implementation_ledger.json`

Those files contain every actual PR returned by the all-state GitHub API at that baseline, including number, title, state, head SHA, merge SHA and the PR-stated implementation scope. This file is the **feature mapping layer** on top of that raw ledger and appends PRs #246–#252. Integer ranges below describe campaigns; they do not assert that every integer in the interval was necessarily a PR if GitHub used a number for a non-PR issue.

Older ledger entries have `changed_files: null` because the first forensic generator did not fetch every PR’s files endpoint. This audit therefore does **not fabricate per-PR filename lists**. Current canonical file ownership is instead given in `WHERE_EVERYTHING_LIVES.md`, and the reachable commit/path history remains in `commit_ledger.csv`. A future mechanical regeneration may enrich the raw ledger with exact per-PR filenames without changing the feature conclusions here.

## Campaign-level PR matrix

| PR(s) | Primary feature/domain | Classification | Canonical effect today | Superseded / historical handling |
|---|---|---|---|---|
| #1 | Imported Personal AI/Vishnu baseline | IMPLEMENTATION / ARCHITECTURE | created repository baseline containing runtime, UI, Memory/Knowledge, tools, devices and other pre-existing systems | pre-import history belongs to upstream Personal AI repo |
| #2 | owner API scope fail-closed repair | HARDENING | not merged as this PR; equivalent/later security boundaries must be evaluated from merged code | CLOSED-UNMERGED; do not count feature from PR alone |
| #3–#6 | mobile PWA conversation/Home/neural Core | UI/UX | foundations of current PWA shell | later UI integrations refine them |
| #7–#18 | stacked Home/Conversation/Timeline/Today/reference UI and preview branches | UI/UX / EXPERIMENTAL | selected work later integrated | many CLOSED-UNMERGED; provenance only unless later recreated |
| #19 | approved main-bound UI integration | UI/UX / IMPLEMENTATION | consolidated approved early PWA owner UI | canonical for that phase, later evolved |
| #20–#29 | session/timezone/dashboard/polish/dialog/responsive/release readiness | UI/UX / HARDENING / QUALIFICATION | current PWA interaction and responsive lineage | later UI truth replaces old taxonomy, not the useful code |
| ~#30–#61 | Vishnu branding, Home/Projects/Today/Memory/Knowledge/Activities/Settings | IMPLEMENTATION / UI/UX | owner-product expansion and project/daily-work surfaces | current 63-screen taxonomy is later authority |
| #62–#96 | Canonical Work, Evidence, Attention, autonomy, recovery, release qualification | IMPLEMENTATION / ARCHITECTURE / QUALIFICATION | canonical durable Work/WorkOrder/Evidence/Claim lineage | remains active; do not build a parallel task truth system |
| #97–#111 | persistent agent E-series | IMPLEMENTATION / ARCHITECTURE | durable agent identity/attempt/effect/evidence and E9 convergence | #97/#98 narrower contracts superseded by #111 convergence |
| #112–#115 | Intelligence Fabric / Agent Workforce | IMPLEMENTATION / UI/UX | specialist agents/teams/provider/budget/failover + owner UI | active but partial acceptance |
| #116 | Visualize / visual intelligence | IMPLEMENTATION / EXPERIMENTAL | current visual-intelligence lineage | active/partial |
| #117–#118 | adaptive intelligence modes/AUTO | IMPLEMENTATION | current routing policy lineage | active |
| #119–#122 | self-improvement, training capture, trained models, release | EXPERIMENTAL / QUALIFICATION | governed training/model lifecycle | experimental; not unrestricted autonomous learning |
| #123–#141 | Portable Intelligence / Vault / packs / fresh-machine / remote-GPU work | IMPLEMENTATION / HARDENING / EXPERIMENTAL | portable/offline/recovery/model-adapter foundations | several stacked drafts superseded by later members of campaign |
| #142 | engineering autonomy boundary | ARCHITECTURE / SECURITY | governed engineering/qualification without blanket repo authority | active boundary |
| #143 | governed release/production automation | RELEASE / PLATFORM | preview/smoke/canary/rollback authority | actual production acceptance still external |
| #144–#148 | qualification evidence/provider telemetry/release monitoring | QUALIFICATION | current evidence/release observability lineage | active/internal |
| #149 | Home/UI hotfix | HARDENING / UI | focused race/polish repair | active if still in current source |
| #150–#164 | Our Products / Product Composer / runners | IMPLEMENTATION / PLATFORM / RELEASE | product definitions, build lifecycle, cross-platform artifact targets | advanced/experimental; signing/store gates remain |
| #165–#182 | Universal Content Intelligence | IMPLEMENTATION / QUALIFICATION | file/document/OCR/semantic/multimodal intelligence | active/partial; real-world model evidence varies |
| #183 | Universal Capabilities | IMPLEMENTATION / SECURITY | OpenAPI + MCP catalog/discovery/governed execution/credentials/mobile management | canonical capability foundation |
| #184 | capability production-target repair | HARDENING / SECURITY | tightened target/mobile/provider boundaries | active security hardening |
| #185 | Capability Forge V1 | EXPERIMENTAL | initial Forge lineage | superseded by V2/V3 |
| #186 | Capability Forge V2 | EXPERIMENTAL | richer plans/forms/automation | superseded by V3 |
| #187 | Capability Forge V3 | EXPERIMENTAL / PLATFORM | current advanced Forge lineage | latest Forge generation; still experimental |
| #188–#191 | Sensorium Native Device Lab | PLATFORM / QUALIFICATION | emulator/simulator/desktop-VM provider/evidence layer | physical L4 still separate |
| #192 | Create/Connect/Restore onboarding | IMPLEMENTATION / SECURITY | owner onboarding foundation | expanded by #220/#251 |
| #193 | QR pairing | IMPLEMENTATION / PLATFORM | device-join UX | active lineage |
| #194 | local TLS/mDNS/fingerprint connectivity | IMPLEMENTATION / SECURITY | local device discovery/connectivity | active lineage |
| #195 | local-first Data Plane | DATA / ARCHITECTURE | placement policies/item-location model/cloud controls | canonical data-policy foundation |
| #196 | encrypted lease-bound data transport | DATA / SECURITY | encrypted transfer/key envelopes | active internal transport |
| #197 | providers/relay/PWA/offline/DR qualification | DATA / QUALIFICATION | provider/offline/continuity expansion | live provider evidence remains external |
| #198 | overlapping stacked data work | DATA | historical/stacked scope | reconcile against later merged Data Plane; do not count separately |
| #199 | atomic one-use/recovery/credential hardening | HARDENING / SECURITY | one-use atomicity improvements | active |
| #200 | SecretVault root-key rotation | HARDENING / SECURITY | crash-safe root-key rotation | current narrowly COMPLETE internal feature |
| #201 | strict hosted config validation | HARDENING / SECURITY | fail-closed sensitive configuration | active |
| #202 | runtime failure observability | HARDENING | exposes/logs formerly silent runtime failures | active |
| #203 | shared SQLite + DeviceRegistry migrations | DATA / ARCHITECTURE | common SQLite foundation | active/internal |
| #204 | MemoryStore migrations | DATA / HARDENING | versioned Memory migration/repair | active |
| #205 | sensitive MemoryStore at-rest encryption lineage | SECURITY / DATA | encrypted sensitive Memory data | active scoped protection |
| #206 | Knowledge/Projects SQLite adoption | DATA / REFACTOR | common migration/storage boundary | active |
| #207 | typed runtime composition | ARCHITECTURE / REFACTOR | explicit runtime boundaries | active |
| #208–#211 | owner-product split/static quality/typing/architecture invariants | REFACTOR / HARDENING | maintainability/composition enforcement | active/internal |
| #212 | locked dependencies | HARDENING / RELEASE | reproducible dependency boundary | active |
| #213 | CycloneDX SBOM | QUALIFICATION / RELEASE | SBOM artifact/gate | active/internal |
| #214 | license compliance | RELEASE / DOCUMENTATION | dependency/license review | active |
| #215 | reproducibility evidence | QUALIFICATION / RELEASE | deterministic/reproducible release evidence | active/internal |
| #216 | encrypted Memory DR | DATA / RELIABILITY | disaster-recovery tests/backup lineage | production restore still not accepted |
| #217 | endurance/concurrency | RELIABILITY / QUALIFICATION | soak/concurrency coverage | active evidence |
| #218 | fault injection | RELIABILITY / QUALIFICATION | failure-path evidence | active evidence |
| #219 | remaining SQLite/product store adoption | DATA / REFACTOR | wider shared SQLite use | active/internal |
| #220 | universal first-device creation | IMPLEMENTATION / PLATFORM / SECURITY | desktop/PWA/native Device 1 model | active/partial acceptance |
| #221 | Markdown notes / portable Knowledge archive | IMPLEMENTATION / DATA | Knowledge portability lineage | current relevance depends on merged state in raw ledger; do not infer from title alone |
| #222 | production readiness/licensing reconciliation | DOCUMENTATION / RELEASE | recorded deployment/volume/license truth | current live state must be reverified separately |
| #223 | initial REA integration | IMPLEMENTATION | first attempt | CLOSED/SUPERSEDED by #224 |
| #224 | official REA 6.5.0 MCP integration | IMPLEMENTATION / INTEGRATION | canonical REA integration | active when external prerequisites exist |
| #225 | proprietary license/security policy | DOCUMENTATION / SECURITY | current all-rights-reserved distribution policy | active policy |
| #226 | cybersecurity assurance | QUALIFICATION / SECURITY | exact-SHA assurance program | active/internal |
| #227 | Vision/Sensorium vision | IMPLEMENTATION / SECURITY | governed visual perception | active/partial |
| #228 | Sensorium context/world model | IMPLEMENTATION / EXPERIMENTAL | richer context/world layer | experimental/partial |
| #229 | Sensorium causal/procedural layer | EXPERIMENTAL | causal/active-perception/procedural research | experimental |
| #230 | production trust/continuity expansion | HARDENING / ARCHITECTURE | trust/work/memory/integration hardening | active |
| #231–#235 | Intelligence Lab phases 1–4 | EXPERIMENTAL / QUALIFICATION | isolated lab/autonomy/compute/performance | remains experimental |
| #236 | OpenVoice | INTEGRATION / EXPERIMENTAL | optional governed voice conversion | external model/provider blocked |
| #237 | Voice Intelligence | IMPLEMENTATION | personas/director/lexicon/evaluation/Voice Studio UX lineage | active/partial |
| #238 | provider-runtime attempt | IMPLEMENTATION | intermediate runtime approach | SUPERSEDED by canonical #239 |
| #239 | canonical voice provider runtime | ARCHITECTURE / IMPLEMENTATION | model-agnostic optional provider boundary | active/config-dependent |
| #240 | voice runtime integration | IMPLEMENTATION / PLATFORM | queues/model manager/Sensorium/device routing | active/partial |
| #241 | VoiceStudio provider | INTEGRATION | optional external/local VoiceStudio | active when installed/configured |
| #242 | VoiceStudio MCP governance | SECURITY / INTEGRATION | routes VoiceStudio tools through Universal Capabilities | active governance |
| #243 | Voice Lab + governed telephony | EXPERIMENTAL / QUALIFICATION | isolated lab and default-off telephony | experimental/external provider blocked |
| #244 | adaptive universal composer | IMPLEMENTATION / UI | intent routing from composer to known product surfaces | active/partial |
| #245 | Universal Storage Fabric | DATA / IMPLEMENTATION | resumable provider transfer/health/encryption/placement/reconciliation | active; live provider acceptance blocked |
| #246 | repository Product Truth audit | DOCUMENTATION / QUALIFICATION | 58-subsystem/240-PR/2407-commit/818-route audit foundation | merged as `4ec735de…`; raw historical authority |
| #247 | duplicate Product Truth audit | DOCUMENTATION | none beyond #246 | CLOSED-UNMERGED, explicitly superseded by #246/main |
| #248 | 29-screen UI audit + Web Companion overlap fix | UI/UX / DOCUMENTATION | draft evidence and useful overlap repair | CLOSED-UNMERGED; useful repair reconciled into #251; taxonomy superseded |
| #249 | stacked 30-screen Data/About UI draft | UI/UX | draft owner Data/About work | CLOSED-UNMERGED; useful changes reconciled by #251; taxonomy superseded |
| #250 | canonical 63-screen UI blueprint | DOCUMENTATION / UI/UX | frozen current owner screen taxonomy | MERGED `1e6e89b64ca67c77c6189d37db8e581997af75f7` |
| #251 | canonical owner UI source gaps | IMPLEMENTATION / UI/UX | all 63 screens source-present; current main | MERGED `5e2b88bff46bca2d4d212731ddad37fe59a7e88a` |
| #252 | owner-facing capability guide | UI/UX / DOCUMENTATION | searchable owner map if merged | OPEN DRAFT; **not current functionality** |

## Merged / open / closed-unmerged interpretation

### Merged PRs

Only merged PRs, plus direct commits reachable from current `main`, can establish canonical current behavior. Current count: **207**.

### Open PRs

Only **#252** is open at the audit cutoff. It is a draft and must not be included in “what Vishnu currently has.” Recommended action: continue → exact-head qualify → merge if the guide remains truthful.

### Closed without merge

Current count: **39**. Their code falls into four categories:

1. **Superseded** — e.g. #223 by #224, #247 by #246/current main, #248/#249 by #250/#251.
2. **Stacked design/reference work later integrated elsewhere** — especially early UI branches #7–#18.
3. **Abandoned/never-canonical** — branch work that never reached main and lacks a later merged equivalent.
4. **Recreated/reconciled** — useful code later landed through another PR/merge.

The raw ledger must be consulted before treating any specific closed PR as current. A closed-unmerged PR description is historical evidence, not product truth.

## Feature → PR reverse matrix

| Feature | Introduced/foundation | Major expansion | Hardening / UI / platform | Canonical today |
|---|---|---|---|---|
| Conversation/PWA | #1, #3–#6 | #19–#29 | #250/#251 truth/UI | current PWA + desktop conversation |
| Memory | #1 | #56/#60 | #204/#205 | `memory/` + owner/governance APIs |
| Knowledge/files | #1 | #165–#182 | #206/#221 | `knowledge/` + `file_intelligence/` |
| Work/Projects | #46/#51/#62 | #63–#93 | #94–#96 | canonical Work + `projects/` |
| Persistent agents | #97–#99 | #100–#108 | #111–#115 | E9 + Agent Workforce |
| Identity/onboarding | #192 | #193/#194/#220 | #251 | universal owner/device model |
| Devices | existing baseline | #183/#188–#194/#220 | #230 | DeviceRegistry/DeviceGateway |
| OpenAPI/MCP | #183 | #184/#224/#242 | #199 security | Universal Capabilities |
| Forge | #185 | #186 | #187 | V3 experimental |
| Data Plane | #195 | #196/#197 | #245/#251 | local-first Data Plane + Storage Fabric |
| Voice | baseline | #236–#240 | #241–#243 | Voice Intelligence + optional runtime; Lab experimental |
| Sensorium | #188–#191 | #227–#229 | #230 | governed Sensorium + experimental intelligence layers |
| Products | #150 | #151–#164 | release/signing gates | Our Products/Product Composer advanced surface |
| Release | #96 | #143 | #212–#226/#251 | governed release/evidence; no fabricated in-app updater |
| UI taxonomy | earlier organic screens | #248/#249 drafts | #250/#251 | 63-screen canonical truth |

## Commit provenance rule

The complete pre-#246 reachable commit history is preserved in `commit_ledger.csv`. Current main is **52 commits ahead** of its `a8d3310…` baseline, making **2,459 reachable commits** at this audit cutoff. Significant merge commits for post-baseline truth are:

- `4ec735de327f2bab6dccb774e2a9c28ef4fc44af` — PR #246 Product Truth audit
- `1e6e89b64ca67c77c6189d37db8e581997af75f7` — PR #250 63-screen UI blueprint
- `5e2b88bff46bca2d4d212731ddad37fe59a7e88a` — PR #251 current main/UI source completion

No audit conclusion should attach dozens of meaningless SHAs when a feature-level milestone/merge SHA identifies the relevant lineage more clearly.