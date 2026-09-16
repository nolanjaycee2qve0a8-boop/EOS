# P0.11 Candidate Validation Plan — Device-Fact Command-Correlation Audit

> **PLANNING-ONLY / NO IMPLEMENTATION EVIDENCE.** This is a prospective test
> and review plan. It reports no executed test, mutation, CI, PR, release, or
> hardware result and grants no implementation authority.

## Validation question

If separately authorized, can an immutable audit evaluate finite caller-owned
inert transmission identity, ACK correlation, actual observation, and explicit
assessment identity/`as_of` facts as PASS/GAP—without creating execution,
replay, or physical-completion authority?

## Future focused matrix

| Area | Required future evidence |
| --- | --- |
| Inert transmission identity | Caller-owned identity/origin/sequence/time fields are preserved for audit and cannot become a command or retry authority. |
| ACK correlation | Exact declared correlation is required; missing, unavailable, malformed, stale, or mismatched facts fail closed as GAP. |
| Actual separation | Actual stays an independent observation; it cannot prove ACK, transmission, command execution, or replace P0.3 reconciliation. |
| Assessment scope | Distinct `assessment_identity` and explicit `assessment_as_of` are required; absent/conflicting/reused scope facts fail closed. |
| Historical evidence | Prior PASS/GAP, ACK, actual, or identity facts cannot hydrate, restore, clone, retime, re-number, or replay authority. |
| Authority negatives | Result/evidence cannot yield a command, request, runtime, adapter, session, continuation, handoff, transmission, or device connection. |
| Frozen boundary | P0.1–P0.10, Residential EMS 1.0, Campaign A–F, and forbidden transport/protocol imports remain unchanged. |

## Future mutation matrix

Any future mutation run must use a clean temporary worktree and record a real
independent failure assertion. At minimum it must attempt to remove or corrupt:

1. inert transmission identity exactness or provenance validation;
2. ACK identity/sequence/origin/time correlation validation;
3. unavailable or malformed fact fail-closed behavior;
4. actual-observation separation from P0.3 reconciliation;
5. assessment identity/`as_of` scope validation;
6. no-hydration/no-replay/no-authority result boundary; and
7. forbidden protocol/network/thread/persistence/HIL imports.

Producer/validator common-mode self-certification, hand-constructed final
PASS/GAP objects, syntax/import failures, incomplete runs, and unrelated
environment errors would not count as mutation kills.

## Future gate order

```text
separate user implementation authorization
→ focused candidate tests
→ upstream / frozen / Campaign A–F regression
→ full pytest with terminal summary and exit code
→ static, import, sensitive-data, generated-output, and pre-commit gates
→ isolated mutation evidence
→ independent read-only review
→ explicit user decision on push / PR / merge
```

This candidate has not entered that sequence. P0.11 does not implement or
authorize protocols, networking, HIL, PCS/BMS/DSP/hardware work, field control,
or physical-completion claims.
