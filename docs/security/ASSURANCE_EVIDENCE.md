# Cybersecurity Assurance Evidence

The Vishnu Cybersecurity Assurance Program produces release evidence for an exact source revision. Evidence is additive to existing CI, reliability/security, SBOM, package, data-plane, qualification-evidence and governed-release checks.

## Evidence produced by this gate

For each run, `security.assurance` produces:

- `cybersecurity-assurance.json` — machine-readable result, exact candidate SHA, checked-out HEAD, control/adversarial/finding counts and blocking errors.
- `cybersecurity-assurance.md` — human-readable summary with the same revision binding and explicit internal-assurance scope.

GitHub Actions uploads both files as a workflow artifact named with the candidate SHA.

## Exact-SHA rule

On pull requests the workflow checks out `github.event.pull_request.head.sha`, not GitHub's synthetic pull-request merge revision. `CANDIDATE_SHA` is passed to the assurance engine, which independently runs `git rev-parse HEAD`. A mismatch is a hard failure.

After any change to the pull-request head, previous assurance evidence is stale and cannot qualify the new head. The new head must run qualification again.

## Fail-closed rules

The gate fails when any of the following is true:

- the candidate SHA is malformed or differs from checked-out HEAD;
- the 11-domain baseline is incomplete or reordered;
- a required control is removed, duplicated, weakened to optional, malformed, or references missing evidence;
- a required adversarial attack category is absent;
- the adversarial corpus is represented as independent third-party work;
- a finding has invalid severity/status metadata;
- any Critical or High finding remains unresolved;
- an unresolved Medium or Low finding lacks explicit owner approval, rationale and a future expiry;
- a Medium/Low risk acceptance has expired.

## Findings lifecycle

`security/findings.json` is the program-level security findings register. A finding should have a stable ID, severity and status. Resolved/closed/fixed findings do not block. Critical and High findings block until resolved. Medium and Low findings may remain open only with bounded owner-approved risk acceptance.

A risk acceptance is not a test waiver: required controls, evidence and adversarial categories still have to pass.

## Relationship to penetration testing

The repository corpus and internal attack simulations are authorized internal security testing. The report always records `independent_third_party_assessment: false`. An external assessor's future penetration-test/audit report remains a separate independent artifact; its findings can be tracked in this lifecycle without relabeling the internal gate as independent.

## Relationship to deployment

PASS means the v1 repository-defined assurance invariants passed for the exact SHA. It does not deploy, authorize deployment, change credentials, modify production, or replace existing release authority.
