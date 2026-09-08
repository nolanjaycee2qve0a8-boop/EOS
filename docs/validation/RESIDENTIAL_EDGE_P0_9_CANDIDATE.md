# P0.9 Provisional Local Validation — Device-Fact Readiness Profile

> **PROVISIONAL LOCAL IMPLEMENTATION — NOT REVIEWED OR RELEASED.** The
> required-ACK-fields repair has local focused evidence of 15 passed in 0.28s
> with exit 0. Scoped Ruff, Ruff format check, mypy, public import smoke,
> forbidden dependency-import scan, `git diff --check`, and P0.1–P0.8 frozen
> production-path checks also passed after this repair. Earlier broader
> regression, full pytest, static-release, and pre-commit evidence predates
> this production change and is superseded; it is not final release evidence.

## 1. Focused local evidence

| Area | Required future evidence |
| --- | --- |
| Explicit PASS/GAP | Deterministic caller profiles/evidence produce explicit PASS or GAP without issuing or accepting a command. |
| Provenance and identity | Missing, conflicting, equal-but-distinct, or unproven identity/provenance claims fail closed. |
| Availability and time | Missing, stale, unknown, inconsistent, or reboot-discontinuous availability/time facts become explicit GAPs. |
| ACK correlation | All six request/ACK ID, sequence, and correlation fields must be explicitly present and exactly match; missing or mismatched claims fail closed, and a correlated ACK never proves physical completion. |
| Actual separation | Actual samples remain separate from P0.3 reconciliation and cannot create command/device authority. |
| Disconnect/reboot | Disconnect, unavailable, and reboot evidence cannot auto-recover; fresh caller evidence is required for reassessment. |
| Authority negatives | Evidence/result copy, serialization, hydration, factory, historical replay, or conversion into runtime/session/adapter/handoff/command authority is rejected. |
| Frozen boundary | P0.1–P0.8, Residential EMS 1.0, and Campaign A–F remain zero-diff. |

The repaired isolated focused run completed locally with 15 passed in 0.28s and
exit 0. It is local test evidence, not a release artifact or a device/field
claim.

## 2. Local mutation evidence and remaining plan

The required-ACK-fields predicate was bypassed only in a cleaned temporary
worktree. The exact missing-ACK focused test then failed because the mutated
assessment became PASS where the test requires GAP with
`ACK_CORRELATION_MISMATCH`; the imported evaluator path was verified to be the
temporary worktree. This is local mutation evidence for the repaired condition.
All prior mutation, broader regression, full pytest, static-release, and
pre-commit evidence predates this production repair and must be refreshed before
release.

The provisional implementation must use isolated mutations and independent
assertions. It must not manually construct final failed results or rely on
producer/validator common-mode self-certification. At minimum, mutations must
be killed for:

1. treating missing, conflicting, stale, or reboot-discontinuous provenance,
   identity, availability, or time as PASS;
2. accepting missing or mismatched ACK correlation fields, or treating a
   correlated ACK as physical completion;
3. allowing actual evidence to replace P0.3 reconciliation or yield authority;
4. reusing historical evidence/profile as an automatic reassessment or retry;
5. leaking a runtime, session, continuation, adapter, handoff, command, or
   factory through result/evidence copy, serialization, or hydration; and
6. introducing direct or from-import transport, network, protocol, threading,
   scheduler, persistence, or HIL dependencies.

Each mutation would require a minimal temporary change, an actual failing test
and assertion, and cleanup evidence. Syntax, import, fixture, or manually
fabricated-final-object failures would not count as a kill.

## 3. Remaining gate sequence

Before release, the required sequence is:

```text
focused P0.9 evidence
→ P0.1–P0.8 upstream/downstream and frozen regressions
→ Residential EMS / Campaign A–F regression
→ full pytest with terminal summary and exit code
→ static, import, sensitive-data, generated-output, and forbidden-dependency scans
→ pre-commit
→ isolated mutation evidence
→ independent review
→ user-approved release decision
```

Only the repaired focused/scoped-static and missing-ACK mutation evidence is
current. Upstream/downstream and frozen regressions, Residential EMS/Campaign
A–F, full pytest, static-release scans, pre-commit, independent review, PR,
CI, merge, and release remain unclaimed until refreshed. This provisional
evaluator neither introduces nor proves protocol, network, HTTP, Modbus, CAN,
serial, thread, scheduler, persistence, auto-retry, HIL, PCS/BMS connection,
DSP/STM32, hardware, field deployment, or safety certification capability.

## 4. Evidence boundary

PASS/GAP assessments remain prospective, immutable audit-only facts over
caller-supplied deterministic evidence. They do not prove device
execution, physical completion, field safety, or deployment readiness. No
learning material is added at this candidate stage because stable production
semantics do not yet exist.
