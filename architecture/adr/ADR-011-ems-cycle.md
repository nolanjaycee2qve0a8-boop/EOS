# ADR-011 — Immutable EMS Decision Cycle

## Status

Accepted

## Context

EOS has an immutable EnergySystemContext, a replaceable EMSPolicy boundary, a
stateless PolicyExecutor, and immutable DecisionResult outputs. These values
need one deterministic execution record without introducing a runtime loop,
scheduler, timer, or policy owner.

Calling policies directly from a cycle would bypass the execution adapter and
duplicate validation. Storing the policy would also turn the cycle from a
result record into a lifecycle owner.

## Decision

Introduce EMSCycle as a frozen slotted dataclass with exactly two fields:

- `context: EnergySystemContext`
- `result: DecisionResult`

Provide `EMSCycle.execute(policy, context)` as a class factory. Delegate
execution exclusively to `PolicyExecutor.execute(policy, context)`, then store
the original context and exact returned DecisionResult.

Do not store the policy. Do not copy, calculate, normalize, or mutate either
recorded value. Propagate PolicyExecutor and policy exceptions unchanged.

## Consequences

- One policy evaluation has one explicit immutable execution record.
- Context and result identity remain available for deterministic inspection.
- Policy invocation remains centralized in PolicyExecutor.
- The cycle owns no policy, infrastructure, clock, or scheduling state.
- Repetition and runtime orchestration require a separate architecture decision.

## Alternatives Considered

- Call `policy.evaluate` directly: rejected because it bypasses the established
  execution adapter.
- Store EMSPolicy on EMSCycle: rejected because a completed cycle records input
  and output, not policy lifecycle.
- Copy context or result: rejected because it would break exact identity and
  could introduce hidden normalization.
- Add a runtime loop or scheduler: rejected because this task represents only
  one deterministic execution unit.
- Update SOC or PowerFlow during construction: rejected because the cycle
  records immutable inputs and outputs without domain calculations.
