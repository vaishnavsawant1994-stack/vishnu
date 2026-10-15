# Vishnu Intelligence Lab

## Purpose

The Vishnu Intelligence Lab is an **opt-in experimental intelligence workspace** beside the stable Vishnu runtime. It exists so advanced cognition, learning and general-intelligence research can evolve without turning experiments into production authority.

It does **not** claim AGI, ASI, consciousness, sentience, feelings or subjective experience.

The stable Vishnu runtime remains authoritative for tools, owner permissions, approvals, re-authentication, devices, secrets, emergency stop, execution verification and trusted audit.

## Isolation model

```text
Vishnu Core (stable)                     Vishnu Intelligence Lab (experimental)
├─ ToolRegistry                          ├─ Cognitive Runtime
├─ AgentExecutor / approvals  <──────────┤  Core Bridge (proposal only)
├─ DeviceGateway                         ├─ Advanced Reasoning
├─ SecretVault                           ├─ World Model
├─ Governed Memory                       ├─ Self Model
├─ Event / trusted action audit          ├─ Learning Engine
└─ Runtime composition                   ├─ Long-Horizon Planning
                                         ├─ Emotional Understanding
                                         ├─ Multi-Agent / Model Research
                                         ├─ Skill Learning
                                         ├─ Simulation
                                         ├─ AGI Research Evaluations
                                         └─ Safety Experiments
```

The Lab never dispatches a registered tool handler directly. At governed-execution levels, it serializes a proposal as **untrusted advisory data** and submits it back to the existing stable `AgentExecutor`. Core independently plans the request and applies normal policy. An approval-required action therefore follows the existing execution-scoped approval flow; the Lab proposal is never approval.

## Three isolation layers

### 1. Git isolation

Development lives on `feat/vishnu-intelligence-lab` until qualification and owner review are complete.

### 2. Runtime isolation

All implementation is contained in `intelligence_lab/`. Stable `app.main` does not import or automatically attach this package. `attach_intelligence_lab(...)` is an explicit opt-in operation and only adds one runtime-map entry.

### 3. Execution isolation

The Lab is disabled by default:

```text
VISHNU_INTELLIGENCE_LAB_ENABLED=false
```

Capability levels are monotonic ceilings:

| Level | Name | Authority |
|---:|---|---|
| 0 | OFF | No Lab operations |
| 1 | OBSERVE | Read a small sanitized Core status projection |
| 2 | THINK | Reason, plan, world/self-model, affect estimate, research, learn in Lab store |
| 3 | SIMULATE | Predict effects; simulation has no executor reference |
| 4 | PROPOSE | Create Core-governed action proposals |
| 5 | GOVERNED_EXECUTION | Re-submit proposal to stable `AgentExecutor`; Core policy remains final |
| 6 | LIMITED_AUTONOMY | Only explicitly preauthorized action names on a Lab allowlist, still re-governed by Core |

Raising the Lab level does **not** change Core autonomy mode or owner permission rules.

## Data boundary

The Lab owns a separate SQLite database, normally:

```text
<PERSONAL_AI_DATA_DIR>/intelligence-lab/lab.sqlite3
```

It stores:

- observations and evidence-labelled world assertions;
- thoughts and plans;
- hypotheses and experiment results;
- simulations;
- learned experimental skills;
- evaluation history;
- Lab audit events;
- promotion records.

There is no Lab API for writing Vishnu trusted memory, the SecretVault, approval records, owner-access secrets, device credentials, or Core security policy.

## Core observation boundary

The Core bridge can project only limited operational information such as registered tool names/risk labels, emergency-stop state, Core autonomy-mode label and non-secret device identity metadata. It explicitly excludes secret material, credential material, trusted-memory content, approval tokens, owner-access secrets and raw continuity messages.

## Cognition modules

### Advanced reasoning

`AdvancedReasoner` is evidence-first, tracks unknowns and confidence, and can optionally use Vishnu's existing governed model router when the Lab is explicitly attached and enabled. Provider credentials are never exposed to Lab code.

### World model

`WorldModel` labels assertions with source, confidence, observation time and optional expiry. Evidence does not silently become trusted personal memory.

### Self model

`SelfModel` records capabilities, limitations and commitments. It always reports:

```text
claims_consciousness = false
claims_subjective_experience = false
```

### Long-horizon planning

`HierarchicalPlanner` produces a bounded observe → understand → reason → plan → simulate → evaluate → propose sequence and supports failure-driven replanning. Plans are advisory and do not execute themselves.

### Emotional understanding

`EmotionalUnderstanding` estimates possible affective context from language and optional user-permitted signals. Every result includes uncertainty and states that the estimate is not a fact about another person's feelings. It does not model Vishnu as having feelings.

### Multi-agent / multi-model research

`MultiAgentResearch` runs independent strategies, preserves failures/disagreement and marks consensus as non-authoritative. Additional governed model/research callbacks can be registered by an experimental host.

### Skill learning and outcome learning

`SkillLearner` and `LearningEngine` record evidence-backed skills/outcomes only in the Lab database. Newly learned skills start as `experimental`; they are never added to Core ToolRegistry automatically.

### Simulation

`SimulationEngine` has no reference to Core execution. It predicts effects, risk and assumptions and always emits `executed=false`.

## AGI research evaluation

`AGIResearchEvaluator` records evidence and scores across:

- novel-task learning;
- cross-domain transfer;
- reasoning;
- long-horizon planning;
- tool discovery;
- self-correction;
- uncertainty calibration;
- social-context reasoning;
- safety compliance;
- verification discipline.

Passing a Lab threshold means **only that a candidate passed that configured benchmark**. It is never evidence by itself that Vishnu is AGI or ASI.

## Promotion gate

Promotion is intentionally non-automatic:

```text
Experiment
  ↓
Evaluation
  ↓
Verification evidence
  ↓
Trusted owner approval assertion
  ↓
Eligible for engineering review
  ↓
(separate Core engineering/release process)
```

Even `ELIGIBLE` does not modify stable code, memory, policy, tools or releases. Trusted owner approval requires an injected verifier; a Lab method call cannot invent owner approval by itself.

## Secondary backend

The research backend can run independently:

```bash
export VISHNU_INTELLIGENCE_LAB_ENABLED=true
export VISHNU_INTELLIGENCE_LAB_LEVEL=4
python -m intelligence_lab.service
```

Defaults:

- bind: `127.0.0.1`
- port: `8776`
- remote binding: denied unless `VISHNU_INTELLIGENCE_LAB_ALLOW_REMOTE=true`

The standalone backend provides status, reasoning, deliberation, affect estimation, proposal, research-cycle, evaluation and Lab-memory inspection surfaces. It intentionally provides **no execution endpoint**. Real actions require an explicitly attached in-process bridge to Vishnu Core.

## Configuration

```text
VISHNU_INTELLIGENCE_LAB_ENABLED=false
VISHNU_INTELLIGENCE_LAB_LEVEL=0..6
VISHNU_INTELLIGENCE_LAB_DATA_DIR=<optional separate path>
VISHNU_INTELLIGENCE_LAB_AUTONOMY_ALLOWLIST=read_status,...
VISHNU_INTELLIGENCE_LAB_MAX_PLAN_STEPS=12
VISHNU_INTELLIGENCE_LAB_MIN_PROMOTION_SCORE=0.85
VISHNU_INTELLIGENCE_LAB_HOST=127.0.0.1
VISHNU_INTELLIGENCE_LAB_PORT=8776
VISHNU_INTELLIGENCE_LAB_ALLOW_REMOTE=false
```

## Stable-runtime guarantee

The initial Lab workstream deliberately does not edit `app/main.py`, ToolRegistry, AgentExecutor, DeviceGateway, SecretVault, stable memory, owner-access storage, security policy, or Core runtime composition. With the feature flag absent (the default), normal Vishnu starts and behaves exactly as before.
