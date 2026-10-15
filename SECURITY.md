# Security Policy

## Supported code

Security fixes are evaluated against the current `main` branch and the latest
owner-approved distributed release, when one exists. Older feature branches,
closed pull requests, abandoned previews, and unqualified development artifacts
should not be treated as supported production versions.

## Reporting a vulnerability

Please report suspected security vulnerabilities privately.

- If GitHub shows a **Report a vulnerability** option for this repository, use
  that private reporting channel.
- Otherwise, contact the repository owner through an authorized private contact
  method associated with the owner's GitHub account.
- Do not include exploit details, credentials, personal data, private keys,
  access tokens, or other sensitive evidence in a public issue, discussion,
  pull request, or commit.

A useful report should include the affected component and revision, the security
impact, reproducible steps or a minimal proof of concept, required privileges or
preconditions, and any suggested mitigation. Remove unrelated personal or secret
data from evidence before sending it.

## Coordinated handling

The maintainer will review reports, determine applicability and severity, and
coordinate remediation and disclosure as appropriate. A report may be closed as
not applicable when it depends on unsupported code, intended owner authority,
unauthorized third-party access, or behavior outside Vishnu's documented trust
boundaries.

Please avoid public disclosure of an unpatched vulnerability until a reasonable
coordinated-remediation process has occurred or the maintainer has confirmed
that public disclosure is appropriate.

## Testing authorization

This policy does not grant permission to access systems, accounts, devices,
networks, repositories, data, providers, credentials, or infrastructure that you
do not own or do not have explicit authorization to test. Do not use destructive
testing, denial of service, social engineering, credential attacks, privacy
invasion, persistence, or data exfiltration against third parties.

Testing should use your own environment or another environment for which you
have explicit authorization, minimize collection of sensitive data, and stop if
unexpected access to private data or systems occurs.

No bug-bounty payment, safe-harbor promise, or broader license to the proprietary
Vishnu code is created by this policy.

## Secrets and incident material

If a report contains a live credential or secret, identify it clearly so it can
be revoked or rotated. Do not commit secrets to a remediation branch. Security
fixes should preserve Vishnu's existing approval, least-authority, audit,
credential-redaction, and fail-closed boundaries unless a reviewed change
explicitly replaces them.

## Third-party vulnerabilities

Vishnu depends on third-party software and services. Reports concerning a
third-party component should identify the dependency and the Vishnu impact. The
third-party project's own security process and license continue to apply to that
component.
