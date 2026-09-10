# P0.10 Planning-Only Candidate Validation — Device-Fact Lifecycle Continuity Profile

> **PROSPECTIVE ONLY.** This is a validation plan for a possible P0.10 phase.
> No P0.10 implementation, test execution, mutation, CI, release, or hardware
> result is claimed here.

## Candidate validation question

Given an explicit, finite, caller-supplied sequence of P0.9-style facts and an
explicit lifecycle transition policy, can a deterministic audit distinguish
valid continuity from disconnect/reboot/reconnect/identity-epoch/time-
discontinuity/fresh-reassessment gaps without creating execution authority?

## Prospective focused matrix

| Category | Required future evidence |
| --- | --- |
| Finite caller facts | Reject empty, non-contract, historical-result, command, transport, or live-authority input. |
| Normal continuity | Explicit continuous identities, time bounds, and fresh facts yield only an audit PASS. |
| Disconnect/reboot | Disconnect and reboot remain GAP; no implicit recovery, replay, or inherited PASS is permitted. |
| Reconnect/identity epoch | Reconnect must present explicit policy-conforming identity/continuity facts; an inherited epoch fails closed. |
| Time discontinuity | Future, stale, non-monotonic where policy forbids it, or unproven time facts yield GAP. |
| Fresh reassessment | A subsequent assessment needs new caller evidence identity; earlier assessment/evidence cannot authorize it. |
| ACK/actual separation | ACK is correlation only; actual remains independent and neither can prove physical completion or replace P0.3 reconciliation. |
| Authority negatives | Result/evidence cannot yield command, runtime, adapter, handoff, session, continuation, transmission, hydration, or replay authority. |
| Frozen/import boundary | P0.1–P0.9 and Campaign A–F remain zero-diff; transport/network/thread/persistence/HIL imports are absent. |

## Prospective mutation evidence

Any future mutation must run in an isolated temporary worktree and record a
real focused/static failure assertion. At minimum, it should remove or corrupt:

1. identity-epoch/continuity validation;
2. transition-policy validation;
3. time-discontinuity or freshness validation;
4. ACK/actual fact separation;
5. fresh-reassessment and historical-evidence no-replay validation; and
6. forbidden transport/import boundary checks.

Producer/validator common-mode self-certification, manually fabricated final
failure objects, syntax/import failures, and incomplete attempts would not be
valid mutation kills.

## Prospective gate order

```text
P0.10 focused
→ P0.9 and predecessor/downstream focused
→ frozen Residential and Campaign A–F regression
→ full pytest with terminating summary and exit code
→ Ruff / format / mypy / import / sensitive / generated-output scans
→ P0.1–P0.9 frozen zero-diff
→ isolated mutation evidence
→ independent read-only review
→ pre-commit
→ user-approved PR, CI, and merge
```

This future plan does not authorize its own execution. It excludes real
protocols, transport, hardware, field control, HIL, and deployment, and it
does not convert PASS/GAP into device readiness or physical-completion claims.
