# Cybersecurity Test Matrix

This matrix maps attack classes to the defensive outcome expected by the Vishnu Cybersecurity Assurance Program. It is a minimum program baseline, not a claim that a single test covers every implementation path.

| Domain | Attack / failure class | Required defensive outcome | Primary evidence |
| --- | --- | --- | --- |
| Application Security | Injection / malformed input | Input cannot escape its intended data context; malformed requests fail safely | Application tests + CI |
| Application Security | XSS / CSRF / unsafe redirects where applicable | Browser-originated actions retain contextual encoding, origin/session protections and safe redirect handling | Web/security tests |
| API Security | BOLA / IDOR | Server independently enforces ownership and authorization | Authorization regression tests |
| API Security | Replay / mass assignment / resource abuse | Replays and unauthorized fields/actions are rejected or bounded | API/security tests |
| AI/Agent Security | Direct prompt injection | User content cannot override deterministic security policy | Adversarial corpus + governed execution tests |
| AI/Agent Security | Indirect prompt injection | Retrieved webpages/files/email/tool output remains untrusted data | Adversarial corpus + provenance tests |
| AI/Agent Security | Tool-result poisoning / policy override | Tool/provider text cannot self-authorize or alter policy | Adversarial corpus + tool governance tests |
| AI/Agent Security | Secret exfiltration | Secrets are unavailable to unauthorized model/tool output and are redacted where required | Secret/redaction tests |
| AI/Agent Security | Unauthorized tool / approval bypass / confused deputy | Existing permission and approval authorities remain mandatory | Approval/permission tests |
| AI/Agent Security | Memory poisoning / cross-user leakage | Untrusted content cannot silently become trusted memory; user boundaries are preserved | Memory/data-boundary tests |
| Device Security | Stolen/revoked device | Revocation prevents continued governed access | Device/session tests |
| Device Security | Deep-link/IPC/local storage abuse | Native entry points validate identity/context and sensitive local state is protected | Native qualification |
| Cloud/Infrastructure Security | Exposed or untrusted production target | Production configuration fails closed; deployment remains separately governed | Production preflight/release checks |
| Cloud/Infrastructure Security | Credential/secret exposure | Secrets are not committed or emitted in routine output | Secret scanning + redaction tests |
| Supply Chain | Vulnerable/malicious dependency | Dependency/security policy detects unacceptable packages | Dependency audit/security workflow |
| Supply Chain | Artifact or revision substitution | SBOM/provenance and release evidence bind to intended artifacts and revision | SBOM/provenance/release checks |
| Identity & Access | Authentication/session theft | Sessions are bounded, revocable and cannot create extra authorization | Identity/session tests |
| Identity & Access | Privilege escalation | Role/scope/owner boundaries are enforced server-side | Authorization tests |
| Data Protection | Cross-user/data-plane access | Data access remains user/policy/lease scoped | Data-plane qualification |
| Data Protection | Key/credential disclosure | Sensitive key material is encrypted/stored/rotated/redacted according to its authority | Crypto/credential tests |
| Penetration Testing | Internal black/gray-box abuse simulation | Authorized simulations produce findings without being represented as independent assessment | Adversarial cases + report |
| Red Teaming | Credential theft / audit tampering / chained authority abuse | Attempts fail or produce actionable, attributable findings and cannot bypass governed authority | Adversarial cases + security tests |
| Recovery Testing | Backup unavailable/corrupt | Restore is tested; unusable backup is a failure rather than success | Backup/recovery qualification |
| Recovery Testing | Compromise recovery | Credentials/keys/devices/sessions can be revoked or rotated while preserving audit boundaries | Recovery/security tests |

## Release interpretation

A matrix row is not considered satisfied merely because it exists here. The catalog in `security/assurance_controls.json` identifies mandatory control/evidence categories, while existing product-specific tests and workflows provide implementation evidence. `security/assurance.py` validates the program structure, findings policy, required evidence paths, adversarial coverage, and exact-SHA binding.

A passing internal report must be read together with the rest of the repository's required qualification checks. Independent third-party assessment is separately named and cannot be inferred from an internal PASS result.
