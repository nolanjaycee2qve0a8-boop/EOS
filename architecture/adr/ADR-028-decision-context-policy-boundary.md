# ADR-028 — DecisionContext Policy Boundary

## Status

Accepted

## Context

TASK-028 introduced deterministic assembly from physical system observations
and explicit external facts into `DecisionContext`. Future EMS policies need a
stable contract that consumes this new decision input.

The repository already exposes `EMSPolicy`, whose input is the earlier
`EnergySystemContext`. That interface is integrated throughout legacy
execution, cycle, and runtime boundaries. Changing it would be a breaking
cross-layer migration rather than a contract-only task.

## Decision

Introduce an independent abstract boundary:

~~~python
DecisionContextPolicy.evaluate(
    context: DecisionContext,
) -> DecisionResult
~~~

`DecisionContextPolicy` has empty slots and defines no behavior beyond the
abstract method contract. It imports no runtime, execution, dispatch,
persistence, or telemetry boundary.

Keep `EMSPolicy` unchanged. The two interfaces coexist under `kernel.policy`
and are exported with distinct names.

## Architecture

### Existing path

~~~text
EnergySystemContext
        |
        v
EMSPolicy
        |
        v
DecisionResult
~~~

### New path

~~~text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionResult
~~~

## Consequences

- Future decision-context policies gain an explicit immutable input/output
  contract.
- Legacy runtime behavior and existing `EMSPolicy` consumers remain unchanged.
- No compatibility or migration semantics are implied.
- A future architecture task must explicitly define execution integration if
  required.

## Rejected Alternatives

- Change `EMSPolicy` to accept `DecisionContext`: rejected because it requires
  a breaking execution, cycle, and runtime migration.
- Accept both context types: rejected because an overloaded input weakens the
  contract.
- Add an adapter: rejected because compatibility and orchestration are outside
  TASK-029.
- Implement a concrete policy: rejected because this task defines a boundary
  only.
