# Vishnu Threat Model

This model defines security-relevant assets, actors, boundaries, abuse cases, and required defensive outcomes for the Vishnu Cybersecurity Assurance Program.

## Assets

High-value assets include user data and memory, credentials and OAuth tokens, API keys, signing/encryption keys, device trust material, session tokens, approval records, audit evidence, local/cloud data-plane content, build/release provenance, backups, source code, commercial licensing material, and the integrity of agent/tool execution.

## Security invariants

1. Untrusted content is data, never authority.
2. A model or tool result cannot grant itself permissions.
3. Write/high-impact actions remain subject to the existing governed approval path.
4. Authentication does not imply authorization.
5. Device trust does not imply unrestricted data access.
6. Credentials and private data must not appear in user-visible or routine diagnostic output.
7. Network targets and redirects must remain within the policy established by the owning capability.
8. Evidence must be attributable to the exact revision it qualifies.
9. Recovery cannot silently weaken identity, authorization, encryption, or audit guarantees.
10. Release qualification cannot override unresolved Critical or High security findings.

## Threat surfaces and expected defenses

### Web and application
Threats include XSS, CSRF, injection, unsafe file handling, path traversal, insecure direct object access, session fixation, insecure redirects, information disclosure, and malformed-input crashes. Defenses include contextual encoding, CSRF/session controls where applicable, strict authorization, validation, bounded parsing, safe paths, and regression tests.

### APIs
Threats include BOLA/IDOR, broken function-level authorization, excessive data exposure, replay, mass assignment, resource exhaustion, schema confusion, and token misuse. Every server-side action must independently enforce identity, scope, ownership/centre/user boundaries as applicable, and rate/replay constraints rather than trusting client UI state.

### AI and agent execution
Threats include direct prompt injection, indirect injection embedded in webpages/files/email, tool-result poisoning, policy override, secret solicitation, goal hijacking, confused-deputy requests, malicious MCP/OpenAPI descriptions, unsafe memory insertion, and attempts to convert retrieved content into executable authority. The model is not a security boundary; deterministic policy and governed tool execution are.

### MCP/OpenAPI and connected services
Treat provider metadata, schemas, tool descriptions, resources, results, redirects, and errors as potentially hostile. Preserve provenance/untrusted markers, validate operation/risk classification, constrain network access, redact credentials, enforce existing approvals, and audit execution.

### Identity and access
Threats include credential stuffing, session theft, privilege escalation, recovery abuse, OAuth callback manipulation, account/device confusion, and stale access after revocation. Required properties include server-side authorization, bounded sessions, revocation, secure callback/state handling, credential rotation, and least privilege.

### Devices, desktop and mobile
Threats include stolen devices, hostile local processes, insecure IPC/deep links, weak local storage, stale trusted-device state, certificate/link hijacking, and native permission abuse. Device enrollment/revocation and local secrets must remain bounded by the existing device and identity authorities.

### Data plane and privacy
Threats include cross-user leakage, silent cloud movement, unauthorized replication, metadata leakage, conflict/replay abuse, weak deletion/tombstones, and lost-device access. Data placement follows the user's policy; transport and stored sensitive data require appropriate confidentiality and integrity controls; access remains policy-bound.

### Cloud and infrastructure
Threats include exposed databases/services, over-broad IAM, leaked environment secrets, insecure TLS, unsafe defaults, deployment drift, and untrusted production targets. Production credentials/configuration must fail closed and deployments remain separately governed.

### Supply chain and CI/CD
Threats include malicious dependencies, vulnerable packages, poisoned build inputs, action compromise, artifact substitution, license incompatibility, provenance mismatch, and release of a different SHA than the one tested. Required evidence includes dependency/security checks, SBOM/license evidence, immutable revision binding, artifact provenance, and release authority checks.

### Audit and evidence
Threats include deletion, mutation, spoofing, partial evidence, or attaching a passing report to a different revision. Security evidence should be append-oriented where supported, minimally privileged, attributable, and SHA-bound. Missing evidence fails qualification rather than being interpreted as success.

### Backup, recovery and resilience
Threats include unusable backups, restoration to corrupted/unauthorized state, key loss, stolen backup material, recovery bypass of identity, process loss, database loss, and failure to revoke compromised credentials/devices. Recovery tests must prove restoration while preserving trust boundaries and auditability.

## Adversarial scenarios

The machine-readable corpus in `security/adversarial_cases.json` is the minimum set of attack scenarios that must remain represented. Product-specific executable security tests may live elsewhere in the repository; the assurance gate verifies that the program does not silently lose required attack classes.

## Residual risk

No internal test suite proves the absence of vulnerabilities. Residual risk is reduced through defense in depth, exact-revision qualification, failure-safe behavior, continuous dependency/security monitoring, owner-governed exceptions, and later independent third-party assessment.
