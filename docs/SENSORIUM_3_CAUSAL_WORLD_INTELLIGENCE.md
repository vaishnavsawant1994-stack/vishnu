# Vishnu Sensorium 3.0 — Causal World Intelligence & Active Perception

Sensorium 3.0 is the intelligence layer above Sensorium 2.0 perception.

It does **not** replace Sensorium 2 permissions, Attention Manager, Temporal World Model,
DeviceRegistry/DeviceGateway, ApprovalManager, Computer Control, Device Control, IoT
action authorities, memory authorities or audit authorities.

The permanent invariant is:

> Knowing what is happening does not grant permission to act.  
> Predicting the correct action does not grant permission to act.  
> Learning how to perform an action does not grant permission to act.

Every Sensorium 3 planning/simulation/learning result reports
`execution_authority=false`. Action proposals still cross Vishnu's existing
approval/policy/control boundary.

## Architecture

```text
Goal / Question
        |
Hypotheses & Task State
        |
Active Perception Planner
        |
Permission + Attention Manager
        |
Sensors / Memory / Device State
        |
Temporal Sensor Fusion
        |
Semantic Scene Graph
        |
Causal World Model
        |
Outcome Simulator
        |
Reasoning / Proposed Action
        |
Approval + Policy + Physical Safety
        |
Computer / Device / IoT Control
        |
Observe Result
        |
Verify -> Learn -> Update World Model
```

## 1. Active Perception Planner

`ActivePerceptionPlanner` ranks candidate observations using:

- expected information gain
- expected uncertainty reduction
- privacy cost
- battery cost
- latency
- sensor availability
- whether a temporary session is already active
- task urgency

The planner refuses unavailable observations and refuses candidates without a
current permission/session. It cannot create a sensor session.

This complements Sensorium 2 Attention Manager:

- Attention Manager: which permitted sensor classes are worth considering.
- Active Perception: what exact observation would reduce uncertainty next.

Example:

```text
Question: Which router light is failing?
Candidate A: closer camera view of WAN LED
Candidate B: microphone environmental audio
Result: choose A if separately permitted because it gives more information
        at lower cost.
```

## 2. Causal World Model

`CausalWorldModel` stores explicit cause/effect hypotheses and evidence.

Evidence classes are separated:

- observation
- temporal precedence
- mechanism
- intervention
- replication
- counterexample
- confounder

The model reports whether a hypothesis remains observational or has direct
intervention support. Counterfactuals are predictions only; Sensorium never
performs the intervention.

Example:

```text
Hypothesis:
  HDMI-B connected -> display on

Evidence:
  display changed after HDMI-B       temporal precedence
  repeated owner-approved reconnect  intervention
```

## 3. Semantic Scene Graph

`SemanticSceneGraph` provides persistent canonical entity identities and
relations across observations.

Examples:

```text
owner -> holding -> screwdriver
screwdriver -> belongs_in -> toolbox
router -> connected_to -> modem
box -> behind -> chair
```

Identity can be resolved from a stable local key and multiple frame aliases.
Every relation preserves source device, modality, timestamp, confidence and
freshness.

## 4. Task-State Intelligence

`TaskStateTracker` stores:

- task purpose
- ordered steps
- current step state
- expected post-state
- checkpoint observations
- uncertainty
- troubleshooting hypotheses
- progress

The task model can represent states such as:

```text
assembly task
  step 7 / 12
  installed screws: 2
  missing screw hypothesis: under packaging
  bracket orientation: uncertain
```

No task-state transition grants action permission.

## 5. Learning From Demonstration / Procedural Memory

`ProceduralMemory` learns reusable step sequences from one or more owner
demonstrations.

It stores:

- steps
- referenced objects
- expected states
- confidence/agreement across demonstrations
- prerequisites
- checkpoints
- safety conditions
- source-device provenance

Durable procedural memory requires explicit owner save.

Learning a procedure never creates execution authority.

## 6. Outcome Simulator / Digital Twin

`OutcomeSimulator` stores bounded declarative action models.

Each model contains:

- preconditions
- deterministic bounded effects
- reversibility
- hazards
- confidence

Supported effect operators are deliberately small: set, toggle and increment.
There is no code execution, dynamic import, shell or action transport.

Example:

```text
Proposed action: disconnect WAN
Precondition: router.power = true
Predicted effect: router.internet = false
Reversible: true
```

Simulation output always says `action_authorized=false`.

## 7. Action–Observation Feedback Loop

`ActionObservationLoop` registers expected effects against an approval
reference and proposed/execution ID. It does not execute that action.

It subscribes to Vishnu's existing durable executor `approval.completed`
event. Only after that authoritative event does a verification move from
`awaiting_execution` to `awaiting_observation`.

It records:

1. expected effects
2. separately selected verification sensors
3. the existing executor's completion signal
4. post-action observations
5. expected-vs-observed comparison
6. verified or mismatch outcome

The loop is therefore:

```text
approved action in existing executor
  -> approval.completed event
  -> Sensorium verification becomes observable
  -> separately permitted sensor evidence
  -> compare expected vs actual
  -> update reasoning/task/world state
```

The Sensorium feedback system is deliberately unable to call Computer Control,
Device Control, IoT action or robotics actuators.

## 8. Physical Skill / Procedure Safety Engine

`PhysicalSafetyEngine` is an independent proposal-safety filter.

Initial high-risk rule families cover:

- mains/high-voltage electrical work
- gas/flame/fuel work
- cutting and power tools
- heat/pressure/steam

Rules include:

- required safe conditions
- stop conditions
- escalation text
- risk classification

The engine can block/escalate a proposal. It cannot approve one.

## 9. Multi-device Unified Reality Model

`UnifiedRealityModel` combines evidence from authenticated/trusted devices into
the existing Temporal World Model plus Semantic Scene Graph.

Evidence keeps:

- source device ID
- modality
- confidence
- freshness
- capture time
- stable/canonical entity identity

The `/sensorium/v3/reality/ingest` API derives the required sensor scope from
the authenticated source device; callers cannot self-assert a `permission_valid`
flag. Sensitive modalities also retain the existing `memory:sensitive`
boundary. Actual sensor capture/session consent remains owned by Sensorium 2.

Multi-device fusion never erases provenance.

## 10. Sensorium Intelligence Benchmark

`SensoriumBenchmark` provides deterministic metrics for:

- object persistence accuracy
- location RMSE
- classification precision / recall / F1
- OCR character error rate
- confidence calibration error
- causal hypothesis accuracy
- task-progress mean absolute error
- battery drain per hour
- privacy violation count/rate

These metrics are for repeatable qualification rather than subjective claims
that the intelligence "looks better."

## Secondary capability foundations

The campaign also adds bounded foundations for later hardware/provider
qualification.

### Long-horizon environmental prediction

`PredictiveEnvironmentModel` performs bounded numeric trend projection with
confidence decay. It does not trigger actions.

### Anomaly detection

`ContextAnomalyDetector` compares new numeric context against bounded history
and reports anomaly score/z-score.

### Better local multimodal routing

`LocalMultimodalRegistry` selects registered local-only models by modality,
operation and input-size capability. It does not download or execute arbitrary
models.

### Indoor positioning / UWB

`IndoorPositioningFusion` fuses already-permitted UWB, LiDAR-anchor, BLE,
Wi-Fi and visual-anchor observations using explicit source weights.

This is a fusion layer. Real UWB hardware support still depends on the
platform/device adapter and physical qualification.

### Matter / HomeKit-style ecosystems

`EcosystemBoundary` exposes observation and action-proposal objects while
keeping action execution outside Sensorium.

A proposal always says:

```text
requires_existing_action_authority = true
action_authorized = false
```

### Robotics

`RoboticsBoundary` deliberately provides robot-state observation and
proposal-only skill descriptions. It does not expose motor/actuator command
transport.

Actual robotics execution must be implemented behind a separate governed
Robot Control authority before any physical actuation can occur.

### Richer LiDAR / room reconstruction

`RoomReconstruction` merges privacy-processed semantic surfaces and anchors
from AR/LiDAR providers. Raw image/video retention is not required.

### Privacy-preserving collaborative perception

`CollaborativePerception` accepts semantic summaries only from entries marked
trusted and permission-valid. Raw image/video/audio/PCM/frame/base64 payloads
are refused.

## API

Sensorium 3 mounts under:

```text
/sensorium/v3
```

The API includes:

- `/status`
- `/perception/plan`
- `/scene/*`
- `/causal/*`
- `/tasks/*`
- `/procedures/*`
- `/simulator/*`
- `/feedback/*`
- `/safety/*`
- `/reality/*`
- `/benchmarks/*`

The secondary foundations are exported Python components used by the
Sensorium runtime and qualification tests. They are not given generic
action-capable HTTP endpoints.

Authentication and device scopes reuse DeviceRegistry.

## Qualification boundaries

### Code implementation

The implementation is considered present when the modules, API integration,
tests and documentation are committed.

### Software qualification

Release qualification requires exact-head CI, security, packaging and
Sensorium 3 qualification jobs to pass.

### Physical hardware qualification

This campaign does not convert emulator/simulator evidence into physical L4
evidence.

UWB, Matter/HomeKit provider transports, LiDAR hardware characteristics,
robotics hardware, wearable/device battery/thermal behavior and physical
actuation require real-device/provider qualification before those specific
hardware claims can be made.

### Production acceptance

Production deployment and production acceptance remain separate release
events.
