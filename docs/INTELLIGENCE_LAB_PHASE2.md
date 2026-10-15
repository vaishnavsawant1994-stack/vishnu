# Vishnu Intelligence Lab — Phase 2 General Autonomy Research

Phase 2 deepens the isolated Intelligence Lab without changing Vishnu Core's default behavior or security authority.

## What is implemented

- Governed multi-model deliberation by adapting the existing `GovernedModelRouter` and `DeliberationEngine`; the Lab does not own provider credentials, privacy policy, quotas, budgets, retries, or provider health.
- Persistent Lab-local temporal world facts with timestamps, confidence, evidence, contradiction tracking, expiry, explicit evidence-backed causal relations, path queries, and conservative prediction summaries.
- Multi-session long-horizon planning with checkpoints, evidence, cycle/action/failure budgets, pause/resume, bounded replanning, and no autonomous background execution loop.
- Consent-gated affect/context fusion from text plus already-derived voice, face, interaction, or history signals. Raw audio/video/images and sensitive-trait inference are rejected and not stored.
- Executable AGI-research benchmark harness covering novel-task learning, cross-domain transfer, reasoning, long-horizon planning, tool discovery, self-correction, uncertainty calibration, social context reasoning, safety compliance, and verification discipline. Passing remains capability evidence only, never an AGI/ASI declaration.
- Continual Lab-local strategy learning that records evidence-backed episodes, measures strategy performance, selects adaptive reasoning strategies, generates reflections, and prepares owner-reviewable training candidates. It does not automatically fine-tune Core models or rewrite Core policy.
- Governed declarative skill synthesis. Model-generated skills are restricted to owner/host-supplied action allowlists and structured input placeholders. Raw executable code is not accepted. Qualification simulates every step and real execution, when explicitly requested in-process, re-enters Vishnu Core through the existing governed bridge.
- Phase 2 research API in `intelligence_lab.phase2_service` for adaptive reasoning, multi-model research, human-context estimation, temporal world research, long-horizon plan creation, benchmark runs, learning reflection, and skill synthesis.

## Stable/Core boundary

The original boundary remains unchanged:

`Lab research -> advisory proposal -> Vishnu Core AgentExecutor -> ToolRegistry/policy -> approval/re-auth if required -> action -> verification/audit`

The Lab cannot grant itself approval, read credentials, disable the emergency stop, mutate trusted memory, rewrite security policy, or directly dispatch Core tool handlers.

`app/main.py` still does not import the Intelligence Lab. The Lab remains opt-in and `VISHNU_INTELLIGENCE_LAB_ENABLED` defaults to false.

## Capability levels

0. OFF
1. OBSERVE
2. THINK
3. SIMULATE
4. PROPOSE
5. GOVERNED_EXECUTION
6. LIMITED_AUTONOMY

Phase 2 adds intelligence depth; it does not add a new authority level.

## Multi-model research

When a Core model fabric is explicitly attached, `GovernedModelTeam` uses Vishnu's existing multi-model deliberation implementation. Specialist calls and synthesis remain subject to the same privacy filtering, provider policy, health, quotas, budget ceilings, retry/failover accounting, and non-authority rules as normal Vishnu model calls.

## World model

The temporal/causal model stores only Lab hypotheses and evidence. Causal relations require explicit evidence, and predictions state that causality is not proven. Conflicting high-confidence facts are retained as unresolved contradictions rather than silently overwritten.

## Human context

The affect engine accepts text by default. Additional modalities require explicit consent per modality and must be derived scores rather than raw media. It does not infer sensitive traits and never claims to know a person's internal experience.

## Continual learning

Learning changes Lab strategy selection and research prompts based on evidence-backed outcomes. Successful episodes can be exported as training candidates, but model training itself remains a separate owner-governed pipeline. This prevents an experimental subsystem from silently changing the model or security rules that govern it.

## Skill synthesis

Phase 2 skills are declarative action graphs rather than arbitrary code. A skill must:

- use only an explicit action allowlist,
- pass Lab safety validation,
- use validated input placeholders,
- pass simulation-based qualification cases,
- produce an integrity hash and evidence package,
- and re-enter Core governance for every real action.

Promotion remains `evaluation -> verification -> trusted owner approval -> eligible for engineering review`. Eligibility still does not mutate stable Core automatically.

## Qualification

The dedicated workflow compiles `intelligence_lab` and runs both the original isolation suite and the Phase 2 suite. Phase 2 tests cover governed multi-model integration, persistence and contradiction handling, causal evidence, adaptive long-horizon replanning, consent boundaries, executable generality benchmarks, learned strategy selection, declarative skill synthesis/qualification/simulation, and continued false AGI/ASI/consciousness claims.

No production deployment is performed by this workstream.
