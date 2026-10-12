# Universal Content Intelligence V1 — Release Qualification

This document freezes the Content Intelligence roadmap at **Stages 0–18**. New capability ideas after Stage 18 are separate future-version work and are not prerequisites for V1.

## Release authority

V1 has two independent authorities:

1. **Repository / production qualification** — implementation, security, recovery, performance, packaging, scope isolation, grounded-answer behavior, model governance, and production integration.
2. **Genuine real-world corpus qualification** — owner-provided, licensed, or public-domain real scans/photos/screenshots/handwriting and visual documents with provenance, source-group isolation, calibration/rejection checks, OCR/HTR thresholds, and visual-task metrics.

The first authority can be fully qualified by hosted CI. It must never substitute for the second.

The canonical release decision is `qualification.content_intelligence_v1.ContentIntelligenceV1ReleaseQualifier`.

## Required repository / production gates

- production ingestion E2E
- Stage 16 grounded document understanding
- Stage 17 scope isolation
- Stage 17 retry/recovery
- Stage 17 versioned reprocessing
- Stage 18 multimodal evidence graph
- Stage 18 grounded visual Q&A
- unsupported-answer rejection
- Knowledge integration
- Projects scope isolation
- model shadow qualification
- owner approval gate
- release-controller activation
- security regression suite
- backup/restore recovery
- performance budget
- Windows packaging
- macOS packaging
- Ubuntu packaging

These gates are fail-closed. A missing or false gate makes the release not qualified.

## Real-world evidence rule

`real_world_corpus_qualified` remains **false** until `Stage18RealWorldEvidenceStore.latest_qualified()` returns persisted passing evidence that:

- explicitly forbids synthetic evidence from qualifying,
- is based on genuine governed sources,
- contains a non-empty corpus,
- meets the Stage 18 minimum independent source-group requirement,
- passed the Stage 18 qualifier.

Synthetic and simulated samples may exercise robustness and regression behavior, but they cannot certify real-world performance.

## Release states

- `not_release_qualified` — one or more repository/production gates are missing.
- `qualified_pending_real_world` — the complete implementation and production-hardening stack is qualified, but genuine real-world corpus evidence has not yet passed.
- `v1_release_qualified` — both repository/production qualification and persisted genuine real-world corpus qualification have passed.

## Permanent product boundaries

- `stage_floor = 0`
- `stage_ceiling = 18`
- `foundation_model = false`
- no model self-approval
- no model self-activation
- extracted content is untrusted data, never tool or instruction authority
- Tesseract remains an external baseline/fallback and is never described as Vishnu-trained
- no release claim may turn `real_world_corpus_qualified` on without persisted genuine evidence

## Current release goal

The release branch closes every repository-controlled V1 qualification and hardening item. If genuine real-world evidence is not present, the correct final state is `qualified_pending_real_world`, not a fabricated V1 production certification.
