# Vishnu Intelligence Lab Phase 3 — Performance, Scale & Adaptive Compute

Phase 3 turns the isolated Intelligence Lab from a capability-rich research
workspace into a measured, adaptive and scalable one. It does **not** create a
new execution/security authority and it does not change normal Vishnu behavior.

## Boundary

The existing boundary remains:

```text
Lab optimization/research
        |
        v
advisory reasoning / placement / DAG / cache / retrieval
        |
        v
existing Vishnu Core bridge
        |
        v
AgentExecutor -> ToolRegistry/policy -> approval/re-auth -> execution
        |
        v
verification + audit
```

`app/main.py` still does not import the Intelligence Lab. The Lab remains
opt-in and fail-closed through the existing
`VISHNU_INTELLIGENCE_LAB_ENABLED` and capability-level controls.

## 1. Adaptive Fast / Smart / Deep reasoning

`adaptive_compute.py` adds a Lab-local complexity classifier and
`AdaptiveReasoningScheduler`.

It reuses Vishnu's existing canonical `AdaptiveStrategy`,
`IntelligenceMode`, `GovernedModelRouter` and `DeliberationEngine` instead of
creating a second model authority.

The scheduler:

- starts with one bounded reasoning pass;
- uses the canonical single / primary+verifier / specialist-race /
  deep-consensus strategy patterns;
- escalates when confidence is low, evidence is contradictory, unknowns remain,
  or task risk/complexity is high;
- compresses context before expensive model-team work;
- can early-exit on adequate confidence;
- records latency/quality/cache evidence for later optimization;
- never grants tool authority.

## 2. Scoped exact + semantic + prefix cache

`cache.py` adds a bounded in-process cache for safe reusable Lab results.

Properties:

- namespace + version + owner/device scope are part of every key;
- sensitive/private/secret entries cannot use a shared scope;
- exact and hashed-token semantic lookup;
- stable-prefix cache for reusable context;
- TTL and LRU bounds;
- raw prompts are never persisted;
- cached values are not written to durable metadata by default;
- cache metadata is Lab-local.

This is intentionally not a cross-owner global response cache.

## 3. Faster Lab memory and retrieval

`LabMemory` now keeps one SQLite connection per thread instead of creating a
connection for every operation. It uses:

- WAL;
- `synchronous=NORMAL`;
- busy timeout;
- in-memory temp storage;
- bounded SQLite page cache;
- indexed time/category reads;
- batched `put_many`;
- `recent_since` for incremental indexing.

`retrieval.py` adds:

- incremental inverted retrieval index;
- bounded hot working set;
- deterministic relevance scoring;
- query-aware context compression;
- content deduplication;
- provenance preservation.

The durable source of truth remains the Lab SQLite database.

## 4. Persistent indexed world graph

`world_index.py` layers indexed SQL tables and in-memory adjacency indexes over
the existing Phase-2 temporal/causal world model.

It provides:

- fact-key/time and source/time indexes;
- cause->effect and effect->cause indexes;
- automatic refresh when Phase-2 writes add facts/relations;
- bounded causal path traversal;
- evidence/source-reliability weighted predictions;
- persistent source reliability scores.

A causal edge remains a hypothesis supported by evidence. Indexing does not
turn correlation into proof.

## 5. Parallel DAG planning

`dag_planner.py` converts an existing Vishnu Lab `Plan` into a dependency DAG.

It computes topological waves and may parallelize only reversible,
parallel-safe research/read/reason/verify/simulate nodes.

Important: the DAG planner has no ToolRegistry, approval or DeviceGateway
authority. A worker that performs real work must still call the existing
governed Core path.

## 6. Performance telemetry and regression gates

`performance.py` captures bounded operational evidence:

- p50/p95/p99 latency;
- success rate;
- quality estimate;
- cost;
- tokens;
- cache hit rate;
- throughput.

It also provides explicit regression budgets. A proposed optimization can be
rejected for latency, reliability, quality, cost or cache regressions.

Raw prompts and credentials are not telemetry fields.

## 7. Continual performance optimization

`optimizer.py` learns which bounded configuration performs best for a class of
task using historical evidence:

```text
depth + model count + cache + parallelism
       -> latency/cost/quality/success evidence
       -> recommendation
```

It does not mutate Core settings automatically. The recommendation remains
Lab-local and owner/release-governed.

## 8. Hardware acceleration and trusted-device placement

Phase 3 reuses Vishnu's existing hardware profiler and trusted DeviceRegistry.

It can:

- inspect/accept CPU/RAM/GPU/VRAM/network/battery metadata;
- recommend Metal/CUDA/ROCm/CPU placement;
- recommend bounded quantization, KV/prefix cache, continuous batching,
  speculative decoding and embedding batching when the underlying runtime
  supports them;
- rank trusted devices using privacy, accelerator, memory, battery and network;
- reject revoked/untrusted devices;
- require local placement for sensitive/private work.

This layer **selects** a target; it does not directly dispatch a command.
Remote execution must still be exposed as an existing governed Vishnu
capability so approvals, device trust and audit cannot be bypassed.

## 9. Phase 3 API

`phase3_service.py` extends the isolated Lab service with endpoints for:

- adaptive reasoning;
- retrieval;
- context compression;
- performance status/gates;
- compute placement/acceleration advice;
- indexed world prediction/source reliability;
- optimizer recommendations.

There is deliberately no Phase-3 `/execute`, raw tool-dispatch,
security-policy-write or credential endpoint.

## Qualification

`tests/test_intelligence_lab_phase3.py` covers:

- Core authority isolation;
- cache scope/privacy and non-persistence of prompts;
- incremental retrieval + compression;
- SQLite connection reuse/WAL/batch writes;
- persistent world indexing;
- DAG dependency waves;
- adaptive reasoning + cache early exit;
- performance regression gates;
- performance-learning optimizer;
- trusted-device placement and acceleration plans;
- 1,000-record bounded scale qualification;
- API privilege absence.

The dedicated Intelligence Lab workflow compiles the Lab and runs Phase 1,
Phase 2 and Phase 3 suites. Repository CI, Reliability/Security, SBOM,
qualification/release and cross-platform package gates remain required before
merge.

## Claims

Phase 3 is performance/general-autonomy research infrastructure. It is not
proof of AGI, ASI or consciousness.
