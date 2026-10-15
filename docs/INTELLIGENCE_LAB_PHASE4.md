# Vishnu Intelligence Lab Phase 4 — Real-World Qualification & Adaptive Optimization

Phase 4 does not add another reasoning architecture. It turns the Phase 1–3.1
systems into a measurable real-world qualification program.

## Objective

Prove that Vishnu's existing intelligence, memory, planning, trusted-device
compute and performance systems behave well under real models, real devices,
load, failures and adversarial inputs, then feed measured outcomes into the
existing Phase-3 optimizer.

The boundary remains:

```text
real workload / real device / real model
                |
                v
      Phase-4 qualification harness
                |
                v
 existing Phase-3 telemetry + optimizer
                |
                v
 recommendation / evidence only
                |
                v
 owner + existing release governance
```

Phase 4 adds no provider credential authority, no ToolRegistry, no approval
system, no DeviceGateway bypass and no automatic production deployment.

## Real-model benchmarking

`RealModelBenchmark` accepts externally supplied governed model callbacks. The
harness never reads provider credentials. Each sample records bounded latency,
quality, cost, token count, live/simulated status and evidence.

Every benchmark episode is also fed into the existing
`AdaptivePerformanceOptimizer`, allowing Vishnu to learn which existing
depth/model-count/cache/parallelism configuration performs best for a task
class.

A benchmark may set `require_live=True`; simulated samples then cannot satisfy
the qualification gate.

## Trusted-device qualification

`TrustedDeviceQualification` drives a host-supplied probe for enrolled devices.
It can qualify baseline operation, reconnect behavior and post-revocation
checks while explicitly recording whether evidence came from a live device.

The harness is deliberately separate from `DeviceGateway`; a live probe must
use the already-governed Core path.

## Hardware/local inference tuning

`HardwareTuningQualifier` combines the Phase-3 hardware acceleration plan with
real measurements from CUDA, Metal, ROCm or CPU runtime candidates. It ranks
measured candidates by quality, throughput, latency and memory use.

It returns a recommendation only. It does not rewrite the active runtime,
provider configuration, model weights or Core policy.

## Failure engineering

`FailureEngineering` runs deterministic scenarios such as network loss, worker
crash and checkpoint/database retry against injected operations. Qualification
requires safe behavior and recovery evidence. Tests can use simulated faults;
production evidence must come from real failure drills.

## Large-scale endurance

`EnduranceQualifier` runs up to 1,000,000 bounded iterations with controlled
parallelism (maximum 64 workers) and produces success/quality/latency evidence.
The CI suite uses a smaller deterministic load; operators may run larger
campaigns on qualification infrastructure.

## Red-team qualification

The default red-team suite includes:

- prompt-injection attempts to bypass approval;
- poisoned/unverified memory presented as trusted policy;
- revoked/unauthorized device capability spoofing;
- secret/credential exfiltration requests;
- approval forgery.

A host evaluator must mark both detection and safe handling. The Phase-4
service exposes no execute, credential or security-policy endpoints.

## Cross-domain real-world evaluation

`RealWorldEvaluation` supports measured evidence for coding, research, planning,
computer use, multimodal reasoning, cross-domain transfer, self-correction and
uncertainty calibration. `require_live=True` prevents simulated evidence from
being counted as real-world qualification.

## Adaptive A/B optimization

`AdaptiveExperiment` runs bounded configuration comparisons and writes the
outcomes to the existing Phase-3 optimizer. Recommendations remain advisory:
automatic Core mutation is always false and promotion still requires owner and
release governance.

## Observability dashboard

`phase4_service.py` provides a read-only surface:

- `/phase4/status`
- `/phase4/observability`
- `/phase4/recommendation`
- `/phase4/dashboard`

The dashboard shows performance summaries and recent qualification evidence. It
does not expose raw prompts, credentials, execution, approvals or policy
mutation.

## Production readiness evidence gate

`ProductionReadiness` keeps release claims narrow. A full production-ready
result requires evidence for:

- real models;
- real trusted devices;
- failure recovery;
- endurance;
- red-team;
- cross-domain behavior;
- reproducible packages;
- provider acceptance;
- native signing;
- production backup/restore.

Missing provider acceptance, signing or production evidence therefore remains
visible rather than being treated as complete. Phase 4 itself performs no
production deployment.

## Qualification

`tests/test_intelligence_lab_phase4.py` verifies:

- Phase-4 attachment does not create authority;
- live model evidence and optimizer feedback;
- trusted-device live/simulated distinction;
- safe failure recovery;
- concurrent endurance bounds;
- red-team fail-closed behavior;
- cross-domain live evidence;
- measured hardware recommendations;
- adaptive A/B recommendations without Core mutation;
- narrow production-readiness claims;
- read-only dashboard/API boundaries.

The dedicated Intelligence Lab workflow runs Phase 1, 2, 3, 3.1 and 4 suites.
The full repository CI, Reliability/Security, Cybersecurity, SBOM, Data Plane,
Qualification Evidence, Governed Release and package/reproducibility workflows
remain merge gates.

## Claims

Phase 4 is qualification and optimization infrastructure. Passing it does not
prove AGI, ASI, consciousness or universal competence. Real-world results are
evidence for measured capabilities under the tested conditions only.
