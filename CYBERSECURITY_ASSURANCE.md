# Vishnu Cybersecurity Assurance Program

Status: v1

Vishnu uses a continuous cybersecurity assurance program rather than treating security as a one-time audit. This program is an evidence and release-qualification layer. It does not replace the product's existing identity, permission, approval, audit, execution, or release authorities.

## Scope

Every qualified release must address these eleven domains:

1. Application Security
2. API Security
3. AI/Agent Security
4. Device Security
5. Cloud/Infrastructure Security
6. Supply Chain
7. Identity & Access
8. Data Protection
9. Penetration Testing
10. Red Teaming
11. Recovery Testing

The penetration-testing and red-team domains in this repository are authorized internal simulations. They must never be described as an independent third-party penetration test or independent security audit. Independent verification requires a separate outside assessor.

## Security objectives

Vishnu must fail closed at trust boundaries; preserve existing authorization and approval requirements; prevent untrusted content from becoming authority; protect credentials, private data, signing material, and encryption keys; maintain auditable provenance; bind qualification evidence to the exact candidate commit; recover safely after failures; and prevent a release from qualifying when material security risk remains unresolved.

## Threat actors

The assurance model considers unauthenticated internet attackers, malicious or compromised users, compromised connected services, malicious API/MCP/OpenAPI providers, hostile webpages/files/email/tool results, compromised devices, malicious dependencies or build inputs, credential thieves, insiders with insufficient authority, and attackers attempting persistence, audit tampering, recovery abuse, or cross-user access.

## Trust boundaries

Important boundaries include user-to-application, application-to-API, agent-to-tool, agent-to-untrusted-content, Vishnu-to-MCP/OpenAPI provider, device-to-server, local-to-cloud data plane, process-to-secret store, CI-to-release authority, build-to-artifact, backup-to-restore, and owner/admin-to-governed actions.

Crossing a boundary never creates authority by itself. Existing policy, identity, permissions, approvals, and audit controls remain authoritative.

## Severity and release policy

Findings use Critical, High, Medium, and Low severity.

- An unresolved Critical or High finding blocks qualification. It cannot be risk-accepted into a passing release.
- An unresolved Medium or Low finding blocks qualification unless it has explicit owner approval, a rationale, and a future expiry date.
- An expired acceptance blocks qualification.
- Missing mandatory controls, required adversarial categories, required evidence, or exact-SHA binding blocks qualification.
- Evidence produced for another commit cannot qualify the candidate.

A passing assurance report means the repository-defined internal assurance requirements passed for that exact revision. It is not a warranty and it is not proof that no vulnerability exists.

## Required assurance activities

The program combines repository security controls and evidence from static checks, secret detection, dependency and license checks, SBOM/provenance validation, authorization tests, malformed-input and boundary tests, AI/agent adversarial cases, replay and privilege-boundary tests, safe recovery exercises, and existing reliability/security qualification workflows.

The adversarial corpus explicitly covers direct and indirect prompt injection, malicious tool results, policy-override attempts, secret exfiltration, unauthorized tool execution, approval bypass, confused-deputy behavior, memory poisoning, cross-user leakage, malicious content, SSRF/path traversal/injection classes, replay/rate-limit abuse, credential theft attempts, audit tampering, backup recovery, and key rotation.

## Exact-revision evidence

`security/assurance.py` validates the catalog, adversarial corpus, findings register, mandatory evidence paths, and candidate commit. It refuses a candidate SHA that does not equal the checked-out Git revision and writes machine-readable and human-readable evidence.

The GitHub Actions workflow checks out the pull-request head revision explicitly rather than relying on the synthetic pull-request merge revision. This makes the resulting report attributable to the exact candidate SHA being qualified.

## Release decision

The assurance gate is additive. Existing required CI, reliability/security, SBOM, package, data-plane, qualification-evidence, and governed-release checks continue to apply. Passing this program alone does not authorize a deployment or production mutation.

Production deployment remains a separate governed action.

## Independent assessment

For mature release stages, Vishnu should also undergo an independent third-party source-code/architecture assessment and penetration test. Findings from that engagement should be entered into the same findings lifecycle without weakening the independent assessor's report or changing the distinction between internal and external verification.
