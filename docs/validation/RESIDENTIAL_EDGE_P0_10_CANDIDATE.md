# P0.10 Restricted Implementation Validation — Device-Fact Lifecycle Continuity Profile

> **MERGED IMPLEMENTATION; VALIDATION EVIDENCE RECORDED.** P0.10 merged through
> PR #207 as `b78425f85fb3ccb7515cf6d69e0d0f2`, and EOS CI `Quality checks`
> succeeded. This is not a hardware-success, device-access, or release-of-field-
> control claim.

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

## Completed local mutation evidence

Eight mutations ran in isolated temporary worktrees and each recorded a real
focused/static failure assertion. The killed guards covered:

1. top-level assessment identity or within-input snapshot/evidence reuse validation;
2. an unlabelled, unknown, or forged transition-label gate;
3. continuity source/epoch/strict-time validation;
4. discontinuity GAP recording or no-erasure validation;
5. reconnect precondition validation;
6. historical assessment/replay input rejection;
7. ACK/actual fusion or missing/defaulted-fact handling; and
8. forbidden transport/import boundary checks.

Producer/validator common-mode self-certification, manually fabricated final
failure objects, syntax/import failures, and incomplete attempts are not valid
mutation kills.

## Recorded local gate evidence

| Gate | Recorded local result | Release meaning |
| --- | --- | --- |
| P0.10 focused | `28 passed` | Implementation-contract regression evidence only. |
| Isolated mutations | 8 guards killed | Evidence that focused/static tests detect the listed semantic regressions. |
| Campaign A–F | `62 passed` | Frozen residential validation remains intact. |
| Full pytest | `2764 passed` | Local repository regression evidence only. |
| Static and frozen checks | Ruff, format, mypy, import/scope/sensitive/generated scans and P0.1–P0.9 frozen diffs passed | No remote CI or release conclusion. |
| Pre-commit | Passed with isolated tool caches | Local hook evidence only; not CI. |

The learning material was committed locally as
`e29342cb3d2e8542803ae9770cd3eb3035085b41` and
`3169469d0ce1ee1aa6fc9cfea51c2f68007cfeb1`; it documents this same merged
audit boundary and does not change production semantics.

## Remaining release gate order

```text
focused / frozen / Campaign / full / static / mutation / pre-commit evidence
→ independent read-only review
→ user-approved PR #207
→ EOS CI `Quality checks` SUCCESS
→ merge to main `b78425f85fb3ccb7515cf6d69e0d0f2`
```

The restricted implementation excludes real
protocols, transport, hardware, field control, HIL, and deployment, and it
does not convert PASS/GAP into device readiness or physical-completion claims.
