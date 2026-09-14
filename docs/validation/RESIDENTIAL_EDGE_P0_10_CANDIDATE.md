# P0.10 Restricted Implementation Validation — Device-Fact Lifecycle Continuity Profile

> **INITIAL IMPLEMENTATION EVIDENCE PENDING.** The user authorized a restricted,
> uncommitted P0.10 test-only implementation. This page states its focused
> validation contract; it does not claim test, mutation, CI, full regression,
> pre-commit, release, or hardware success until those results are recorded.

## Validation question

Given an explicit, finite, caller-supplied sequence of P0.9-style facts and an
explicit lifecycle transition policy, can a deterministic audit distinguish
valid continuity from disconnect/reboot/reconnect/identity-epoch/time-
discontinuity/identity-reuse/replay gaps without creating execution authority?

## Focused matrix

| Category | Required implementation evidence |
| --- | --- |
| Finite caller facts | Reject empty, non-contract, historical-result, command, transport, or live-authority input. |
| Normal continuity | Explicit continuous identities, time bounds, and fresh facts yield only an audit PASS. |
| Disconnect/reboot | Disconnect and reboot remain GAP; no implicit recovery, replay, or inherited PASS is permitted. |
| Reconnect/identity epoch | Reconnect must present explicit policy-conforming identity/continuity facts; an inherited epoch fails closed. |
| Time discontinuity | Future, stale, non-monotonic where policy forbids it, or unproven time facts yield GAP. |
| Top-level audit identity | One caller-owned input has a distinct assessment identity and unique within-input snapshot/evidence identities; reuse is GAP and a historical assessment/result input is rejected. |
| ACK/actual separation | ACK is correlation only; actual remains independent and neither can prove physical completion or replace P0.3 reconciliation. |
| Authority negatives | Result/evidence cannot yield command, runtime, adapter, handoff, session, continuation, transmission, hydration, or replay authority. |
| Frozen/import boundary | P0.1–P0.9 and Campaign A–F remain zero-diff; transport/network/thread/persistence/HIL imports are absent. |

## Frozen semantic cases

Focused tests use the closed transition set `CONTINUITY`,
`DISCONNECT`, `REBOOT`, `RECONNECT`, `IDENTITY_EPOCH_CHANGE`,
`TIME_DISCONTINUITY`; unknown, duplicated, or absent
labels must produce `UNLABELLED_OR_UNKNOWN_TRANSITION` GAP. The minimum
contract cases are:

| Case | Required result |
| --- | --- |
| Continuity | Both available with same source/epoch, strictly increasing observed time, valid `as_of`/max-age, and new evidence identity; otherwise `CONTINUITY_FACT_MISMATCH` GAP. |
| Disconnect/reboot/epoch/time discontinuity | Each records its exact explicit GAP category and validates its documented source/epoch/time pair facts; it cannot be represented as continuity or erased by a later fact. |
| Reconnect | Only follows a declared discontinuity and needs available complete facts, same source, changed epoch, strictly increasing time, and new evidence identity; otherwise `RECONNECT_PRECONDITION_UNMET` GAP. |
| Stateless top-level audit | Assessment identity differs from all snapshot/evidence identities, and all sequence positions are unique; reuse yields `ASSESSMENT_OR_EVIDENCE_IDENTITY_REUSED`, while historical assessment/result input yields `HISTORICAL_ASSESSMENT_INPUT_REJECTED`. Cross-call newness is intentionally not asserted. |
| Overall status | PASS only with zero GAP records and fully conformant transitions; any finite sequence containing a discontinuity is GAP. A later independent caller input is a new audit, not history repair. |
| ACK/actual | Exact correlation-only ACK and separate actual presence are required; missing, fused, or defaulted-`None` facts yield `ACK_ACTUAL_FACT_MISSING_OR_FUSED` GAP and never prove completion. |

## Future mutation evidence

Any future mutation must run in an isolated temporary worktree and record a
real focused/static failure assertion. At minimum, it should remove or corrupt:

1. top-level assessment identity or within-input snapshot/evidence reuse validation;
2. an unlabelled, unknown, or forged transition-label gate;
3. continuity source/epoch/strict-time validation;
4. discontinuity GAP recording or no-erasure validation;
5. reconnect precondition validation;
6. historical assessment/replay input rejection;
7. ACK/actual fusion or missing/defaulted-fact handling; and
8. forbidden transport/import boundary checks.

Producer/validator common-mode self-certification, manually fabricated final
failure objects, syntax/import failures, and incomplete attempts would not be
valid mutation kills.

## Remaining gate order

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

The restricted implementation excludes real
protocols, transport, hardware, field control, HIL, and deployment, and it
does not convert PASS/GAP into device readiness or physical-completion claims.
