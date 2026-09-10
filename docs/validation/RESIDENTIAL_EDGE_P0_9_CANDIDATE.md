# P0.9 Provisional Local Validation — Device-Fact Readiness Profile

> **MERGED MAIN RECORD — PR #203 CI SUCCESS.** P0.1–P0.9 focused suites passed; the
> Residential frozen regression reported 530 passed and 62 deselected; Campaign
> A–F reported 62 passed in 978.15s with exit 0; and full pytest reported 2736
> passed in 716.52s with exit 0. The earlier code-stage pre-commit completed its
> four hooks with exit 0 and zero working-tree pollution. A later isolated
> pre-commit after the learning-example Ruff format edit was not PASS: its
> pytest hook reported 2587 passed and 149 errors when a relative project
> `.pytest_cache` basetemp hit Windows `WinError 5`; Ruff, format, and mypy
> passed. That local failure is not counted as PASS. PR #203 then passed remote
> Quality checks, independently validating the formatting fix, and merged
> normally to main at `4690d47cbfa4cac0ae4eb4e9a27b722d68aa17a7`. This repository
> merge is not a hardware, field, deployment, or production readiness claim.

## 1. Focused local evidence

| Area | Final local evidence |
| --- | --- |
| Explicit PASS/GAP | Deterministic caller profiles/evidence produce explicit PASS or GAP without issuing or accepting a command. |
| Provenance and identity | Missing, conflicting, equal-but-distinct, or unproven identity/provenance claims fail closed. |
| Availability and time | Missing, stale, unknown, inconsistent, or reboot-discontinuous availability/time facts become explicit GAPs. |
| ACK correlation | All six request/ACK ID, sequence, and correlation fields must be explicitly present and exactly match; missing or mismatched claims fail closed, and a correlated ACK never proves physical completion. |
| Actual separation | Actual samples remain separate from P0.3 reconciliation and cannot create command/device authority. |
| Disconnect/reboot | Disconnect, unavailable, and reboot evidence cannot auto-recover; fresh caller evidence is required for reassessment. |
| Authority negatives | Evidence/result copy, serialization, hydration, factory, historical replay, or conversion into runtime/session/adapter/handoff/command authority is rejected. |
| Frozen boundary | P0.1–P0.8, Residential EMS 1.0, and Campaign A–F remain zero-diff. |

The focused P0.9 suite completed locally with 15 passed and exit 0. The broader
local gate facts are recorded in the candidate banner; they are not a release
artifact or a device/field claim.

## 2. Valid local mutation evidence

Seven current-head mutations were run only in cleaned temporary worktrees and
were killed by independent focused or static assertions: identity/provenance,
future timestamp, supplied ACK mismatch, missing six-field ACK correlation,
actual-presence separation, fresh reassessment, and package-level forbidden
imports. The missing-ACK mutation made the assessment PASS where the focused
test requires GAP with `ACK_CORRELATION_MISMATCH`; the imported evaluator path
was verified to be the temporary worktree.

The candidate uses isolated mutations and independent assertions. It does not
count syntax, import, fixture, manually fabricated-final-object, incomplete, or
incorrectly-targeted mutation attempts as kills.

## 3. Completed publication record and next-stage boundary

The completed repository publication sequence was:

```text
independent final review
→ user-approved push
→ Draft PR
→ remote Quality checks SUCCESS
→ ordinary PR #203 merge to main
```

The local focused, frozen, Campaign A–F, full pytest, static-release,
pre-commit, and mutation gates are recorded, and the final review, PR, remote
CI, and ordinary merge are complete. This historic candidate evaluator neither
introduces nor proves protocol, network, HTTP, Modbus, CAN, serial, thread,
scheduler, persistence, auto-retry, HIL, PCS/BMS connection, DSP/STM32,
hardware, field deployment, or safety certification capability. Any next stage
must begin with a new capability-gap review and explicit user approval.

## 4. Evidence boundary

PASS/GAP assessments remain prospective, immutable audit-only facts over
caller-supplied deterministic evidence. They do not prove device execution,
physical completion, field safety, or deployment readiness. Locally integrated
learning material explains this candidate boundary without changing its
provisional status or creating stable production semantics.
