# P0.9 Candidate Only Validation Plan — Device-Fact Readiness Profile

> **CANDIDATE ONLY — PLANNING APPROVED.** No P0.9 implementation, test result,
> release gate, or PASS result exists yet. The matrix below is a future evidence
> plan and must not be read as completed validation.

## 1. Future focused-test plan

| Area | Required future evidence |
| --- | --- |
| Explicit PASS/GAP | Deterministic caller profiles/evidence produce explicit PASS or GAP without issuing or accepting a command. |
| Provenance and identity | Missing, conflicting, equal-but-distinct, or unproven identity/provenance claims fail closed. |
| Availability and time | Missing, stale, unknown, inconsistent, or reboot-discontinuous availability/time facts become explicit GAPs. |
| ACK correlation | ID, sequence, and correlation claims are assessed as audit facts only; mismatches fail closed and correlated ACK never proves physical completion. |
| Actual separation | Actual samples remain separate from P0.3 reconciliation and cannot create command/device authority. |
| Disconnect/reboot | Disconnect, unavailable, and reboot evidence cannot auto-recover; fresh caller evidence is required for reassessment. |
| Authority negatives | Evidence/result copy, serialization, hydration, factory, historical replay, or conversion into runtime/session/adapter/handoff/command authority is rejected. |
| Frozen boundary | P0.1–P0.8, Residential EMS 1.0, and Campaign A–F remain zero-diff. |

## 2. Future mutation plan

Any future implementation must use isolated mutations and independent
assertions. It must not manually construct final failed results or rely on
producer/validator common-mode self-certification. At minimum, mutations must
be killed for:

1. treating missing, conflicting, stale, or reboot-discontinuous provenance,
   identity, availability, or time as PASS;
2. accepting an ACK correlation mismatch or treating a correlated ACK as
   physical completion;
3. allowing actual evidence to replace P0.3 reconciliation or yield authority;
4. reusing historical evidence/profile as an automatic reassessment or retry;
5. leaking a runtime, session, continuation, adapter, handoff, command, or
   factory through result/evidence copy, serialization, or hydration; and
6. introducing direct or from-import transport, network, protocol, threading,
   scheduler, persistence, or HIL dependencies.

Each mutation would require a minimal temporary change, an actual failing test
and assertion, and cleanup evidence. Syntax, import, fixture, or manually
fabricated-final-object failures would not count as a kill.

## 3. Future gate sequence

If implementation is separately authorized, the minimum proposed sequence is:

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

None of these gates has run for P0.9. This candidate neither introduces nor
proves protocol, network, HTTP, Modbus, CAN, serial, thread, scheduler,
persistence, auto-retry, HIL, PCS/BMS connection, DSP/STM32, hardware, field
deployment, or safety certification capability.

## 4. Evidence boundary

Future PASS/GAP assessments would remain prospective, immutable audit-only
facts over caller-supplied deterministic evidence. They would not prove device
execution, physical completion, field safety, or deployment readiness. No
learning material is added at this candidate stage because stable production
semantics do not yet exist.
