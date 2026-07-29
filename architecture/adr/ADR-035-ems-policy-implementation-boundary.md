# ADR-035 ? EMS Policy Implementation Boundary

## Status

Accepted

## Context

`DecisionContextPolicy` defines the stable input and output contract for the
new decision path. Future policy implementations need an explicit extension
seam without changing that contract, overloading legacy `EMSPolicy`, or
introducing a real EMS strategy into the kernel foundation.

## Decision

Introduce `DecisionContextPolicyImplementation` as an abstract, stateless
subclass of `DecisionContextPolicy`.

It inherits:

~~~python
evaluate(
    context: DecisionContext,
) -> DecisionContextResult
~~~

and adds no implementation. Future concrete policies subclass this boundary
and implement `evaluate()`.

## Architecture

~~~text
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextPolicyImplementation
        |
        v
Future Concrete Policy
        |
        v
DecisionContextResult / DecisionIntent
~~~

## Identity and Ownership

The boundary does not transform policy inputs or outputs. A concrete policy's
exact `DecisionContextResult` and `DecisionIntent` references pass through
unchanged.

The boundary has empty slots and owns no runtime, dispatcher, device,
persistence, cache, history, or implementation instance state.

## Consequences

- Concrete policies have an explicit extension point.
- The existing `DecisionContextPolicy` contract stays stable.
- Legacy `EMSPolicy` and all runtime/execution consumers remain unchanged.
- No strategy is selected or implemented by this decision.

## Rejected Alternatives

- Add a concrete idle, charge, or discharge policy: rejected because it would
  introduce strategy behavior.
- Modify or overload legacy `EMSPolicy`: rejected because the legacy and new
  decision paths remain independent.
- Add optimization or forecast services: rejected because they belong to
  future capabilities.
- Store runtime or device dependencies: rejected because policy evaluation
  remains a pure decision boundary.

## Non-goals

- SOC algorithms, TOU logic, PV strategy, or battery control.
- Optimization, forecasting, scheduling, or recommendations.
- Commands, dispatch, runtime, device control, or protocols.
- Persistence, telemetry, cache, or history.
