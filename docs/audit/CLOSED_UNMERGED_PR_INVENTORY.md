# Closed-Unmerged Pull Request Inventory

**Audited repository:** `vaishnavsawant1994-stack/vishnu`  
**Audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Audit date:** 2026-10-17

GitHub currently reports **39 pull requests that are closed without merge**. They are historical evidence only. Nothing in this table is counted as current functionality merely because a branch once implemented it.

| PR | Title | Historical disposition | Current-product treatment |
|---:|---|---|---|
| #2 | Fail closed when owner API scope authorization is unavailable | Security hardening draft with a frozen qualified head, but explicitly never merged | Do not credit #2 itself. Later merged owner-scope/security hardening is the canonical source of current behavior. |
| #7 | UI: compact color-shifting original sphere + approved mobile Home | Early stacked UI candidate | Superseded/absorbed by the main-bound owner-UI integration and later PWA work. |
| #8 | Complete right-side timeline: real chats, meetings, tasks, work and completion history | Stacked Timeline candidate | Historical precursor; later main-bound PWA/Timeline work is canonical. |
| #9 | Bind cloud data to independent installation identities | Stacked preview/runtime-isolation candidate | Historical evidence only; current deployment/security boundaries come from later merged runtime hardening. |
| #10 | Fix signed-out timeline loading and clear cached rows | Stacked Timeline/session repair | Historical precursor; current session/PWA behavior is evaluated from main. |
| #11 | Approved open conversation layout with canonical message time | Qualified draft UI | Its useful design lineage was incorporated through later main-bound UI work; #11 itself never merged. |
| #12 | Unify Personal AI product-wide design system across web, desktop and companions | Stacked product-wide design draft | Superseded by later merged design-system/platform polish work. |
| #13 | Preview deployment: complete Personal AI UI finishing with existing runtime safeguards | Isolated preview branch/deployment | Preview evidence only; not current production or canonical merge. |
| #14 | Complete Personal AI UI finishing and preview safety fixes | Preview/UI repair candidate | Historical; current source is evaluated from later merged UI work. |
| #15 | UI: approved Personal AI Home reference | Stacked Home candidate | Explicitly part of the UI lineage consolidated through later main-bound work. |
| #16 | Implement approved Conversations sidebar | Stacked Conversations candidate | Historical precursor; later owner UI is canonical. |
| #17 | Timeline sidebar — approved premium reference | Qualified Timeline candidate | Historical precursor; later PWA Timeline implementation is canonical. |
| #18 | Today / Tasks — approved daily planning screen | Stacked Today candidate | Historical precursor; later main Today/Work surfaces are canonical. |
| #23 | Test and serve the approved iPhone PWA dashboards | PWA-serving/preview candidate | Closed without merge; later PWA/dashboard merges supersede it. |
| #69 | feat: add safe versioned replanning | Duplicate/stacked Work replanning candidate | Canonical versioned replanning already entered main through merged Work-orchestration lineage (notably #66 and later Project Work integrations). |
| #97 | test/docs: CL4R1T4S clean-room planner contracts and Vishnu integration map | Unmerged contract/research precursor | Do not count as current feature. Later merged persistent-agent program is canonical where equivalent behavior exists. |
| #98 | feat(tools): optional typed validation hooks for tool inputs and outputs | Unmerged typed-tool contract precursor | Do not assume these exact hooks exist from #98; verify current ToolRegistry/tool contracts directly. |
| #103 | E-series persistent-agent intermediate draft | Unmerged E-series precursor | Superseded/converged by the later merged E-series integration, culminating in #111. |
| #104 | E-series persistent-agent intermediate draft | Unmerged E-series precursor | Superseded/converged by the later merged E-series integration, culminating in #111. |
| #112 | Agent Workforce predecessor | Stacked Agent Workforce draft | Superseded by merged PR #114, whose body explicitly states it contains the complete Agent Workforce program from #112/#113. |
| #113 | Agent Workforce predecessor | Stacked Agent Workforce/UI draft | Superseded by merged #114; later #115 further refined the UI. |
| #125 | Portable Intelligence intermediate draft | Stacked portability candidate | Superseded by later merged Portable Intelligence work, including the later consolidated tranche (#128 lineage). |
| #127 | Portable Intelligence intermediate draft | Stacked portability candidate | Superseded/reconciled by later merged Portable Intelligence work. |
| #131 | Portable Intelligence intermediate draft | Stacked portability candidate | Superseded/reconciled by later merged Portable Intelligence work. |
| #133 | Portable Intelligence intermediate draft | Stacked candidate | Superseded by its later merged successor in the same campaign (#137 lineage). |
| #134 | Portable Intelligence intermediate draft | Stacked candidate | Superseded by its later merged successor in the same campaign (#138 lineage). |
| #135 | Portable Intelligence intermediate draft | Stacked candidate | Superseded by its later merged successor in the same campaign (#139 lineage). |
| #136 | Portable Intelligence intermediate draft | Stacked candidate | Superseded by its later merged successor in the same campaign (#140 lineage). |
| #145 | Add physical-device release orchestration | Draft physical-device release workflow | Superseded by merged #146, which explicitly starts from #145 and completes the owner-run physical-device acceptance package. |
| #152 | Our Products intermediate productization/build draft | Stacked Our Products candidate | Superseded by merged #155, whose PR states it integrates #152 and #154 changes into the qualified foundation. |
| #154 | Our Products intermediate commercial/runtime draft | Stacked Our Products candidate | Superseded by merged #155. |
| #156 | Our Products commercial/runtime follow-on draft | Unmerged follow-on | Do not count #156 itself. Current Our Products truth comes from merged #150/#155 and later merged runner/build/distribution work actually reachable from main. |
| #188 | Sensorium Native Device Lab foundation draft | First native-lab integration attempt | Superseded by merged #191, which delivers the Android Emulator, iOS Simulator and hosted-VM integration as one qualified program. |
| #198 | Local-first Data Plane/provider continuation draft | Stacked data-plane candidate | Superseded/reconciled by the merged Data Plane/provider lineage, especially #197 and later #245 Storage Fabric. |
| #223 | Initial REA integration | First REA attempt | Superseded by merged canonical #224 using official REA 6.5.0 local stdio MCP. |
| #238 | Initial voice provider runtime | First provider-runtime attempt | Superseded by merged canonical #239 and integration #240. |
| #247 | Duplicate Product Truth audit | Duplicate audit branch | Closed because merged #246/current main already contained the Product Truth audit. |
| #248 | 29-screen UI audit + Web Companion overlap repair | Draft UI audit | Taxonomy superseded by merged #250; useful repair reconciled into #251. |
| #249 | 30-screen/Data & Storage/About stacked UI draft | Draft UI audit/implementation | Taxonomy superseded by #250; useful source changes reconciled into #251. |

## Exact closed-unmerged PR numbers

`2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 23, 69, 97, 98, 103, 104, 112, 113, 125, 127, 131, 133, 134, 135, 136, 145, 152, 154, 156, 188, 198, 223, 238, 247, 248, 249`

## Forensic rule

A closed-unmerged PR may prove that code was written or qualified on a historical branch, but it does **not** prove Vishnu currently has that behavior. This audit counts it as current only when the behavior is independently present in current `main` through a later merged implementation.

## Changed-file evidence limitation

The original 240-PR machine ledger generated by PR #246 did not persist per-PR changed-file arrays (`changed_files` is `null` there). For merged PRs, path-level history remains recoverable from the reachable commit ledger because merge commits carry changed-file sets. For these 39 closed-unmerged branches, GitHub’s bulk PR-diff endpoint is capped at 300 files across the request, so this audit does not fabricate a complete filename array for every abandoned branch. PR bodies that explicitly name files are retained as evidence, and current-product file ownership is mapped separately in `WHERE_EVERYTHING_LIVES.md`.

This limitation does not change current-product conclusions because none of these 39 PRs is treated as current solely from its unmerged branch.