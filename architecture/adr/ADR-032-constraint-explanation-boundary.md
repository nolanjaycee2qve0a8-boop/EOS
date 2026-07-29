# ADR-032 ? Constraint Explanation Boundary

## Status

Accepted

## Context

TASK-032 introduced a stateless constraint boundary and immutable
`FeasibleDecisionIntent`. A later consumer may need to observe the exact
relationship between a completed feasible result and its source intent without
re-running constraint evaluation or introducing execution behavior.

## Decision

Introduce `ConstraintExplanation` as a frozen, slotted observation containing:

~~~python
feasible_intent: FeasibleDecisionIntent
source_intent: DecisionIntent
~~~

The explanation preserves the exact source references. Following the TASK-039
lineage refinement, `create(feasible_intent, source_intent)` receives both
completed artifacts explicitly. The feasible inner intent may preserve the
source identity or may be a different immutable intent produced by constraint
adjustment. The method constructs no replacement lifecycle or domain objects.

## Architecture

~~~text
DecisionIntent
        |
        v
DecisionConstraintBoundary
        |
        v
FeasibleDecisionIntent
        |
        v
ConstraintExplanation
~~~

## Consequences

- Constraint evidence can be observed through a stable immutable contract.
- Exact policy source identity and exact feasible result identity remain
  available to future presentation or audit boundaries.
- Explanation remains independent from evaluation, execution, and storage.
- Adding human-readable or derived explanations requires a separate
  architecture decision.

## Rejected Alternatives

- Re-run the constraint boundary: rejected because explanation is observation,
  not evaluation.
- Copy or serialize the source objects: rejected because value copies lose
  identity evidence.
- Add reason or recommendation fields: rejected because TASK-033 prohibits
  derived reasoning.
- Include commands or events: rejected because those belong to later
  execution layers.
- Add SOC, power, device, optimization, or forecast data: rejected because the
  explanation has no ownership of those domains.

## Non-goals

- Constraint evaluation or algorithms.
- Derived reasoning, diagnosis, or recommendations.
- Runtime, dispatch, device, persistence, or telemetry integration.
- Commands, events, optimization results, or forecast data.
- Cache, history, or mutable state.
