# TASK-040 - Grid Constraint Boundary

## Status

IN REVIEW

## Objective

Introduce the abstract boundary through which future grid-side physical
constraints can evaluate an immutable `DecisionIntent`.

TASK-040 defines an extension seam only. It does not implement an import limit,
export limit, zero-export algorithm, pricing strategy, optimization,
forecasting, device command, or runtime integration.

## Architecture

~~~text
source DecisionIntent
        |
        v
GridConstraintBoundary
        |
        v
FeasibleDecisionIntent
~~~

`GridConstraintBoundary` specializes the existing general constraint contract:

~~~python
evaluate(intent: DecisionIntent) -> FeasibleDecisionIntent
~~~

The signature is identical to
`DecisionConstraintBoundary.evaluate(intent)`. The general boundary,
`DecisionIntent`, policy contracts, and source/feasible lineage are unchanged.

## Boundary Contract

`GridConstraintBoundary`:

- inherits `DecisionConstraintBoundary`;
- is abstract;
- has empty slots and retains no instance state;
- accepts exactly one existing immutable `DecisionIntent`;
- returns `FeasibleDecisionIntent`; and
- does not define a concrete constraint algorithm.

Future concrete implementations may receive immutable evaluation facts through
construction. Possible facts include:

- grid import limit in kW;
- grid export limit in kW; and
- zero-export capability.

These facts and their validation are intentionally not fields of the abstract
boundary. Their exact contracts belong to future implementation tasks.

## Intent Lineage

TASK-039 remains authoritative:

~~~python
cycle.source_intent is cycle.result.intent
cycle.explanation.source_intent is cycle.source_intent
cycle.explanation.feasible_intent is cycle.feasible_intent
~~~

A future grid constraint may preserve the source intent identity when no
adjustment is needed or return a new immutable feasible intent when adjustment
is required. TASK-040 performs neither behavior because it introduces no
implementation.

## Dependency and Ownership Rules

The boundary owns no:

- grid facts;
- policy, runtime, dispatcher, or device instance;
- cache, history, persistence, or telemetry state; or
- pricing, optimization, or forecasting engine.

It does not modify `DecisionConstraintBoundary`,
`DecisionEvaluationOrchestrator`, `DecisionIntent`, or legacy contracts.

## Non-goals

- Zero-export or anti-backflow algorithms.
- Grid import or export limiting.
- TOU or electricity-price strategy.
- Optimization or forecasting.
- PCS, BMS, CAN, Modbus, or device commands.
- Dispatch, runtime, execution, persistence, or telemetry.
- A concrete production grid constraint implementation.
- Changes to source/feasible intent lineage.

## Tests

Focused tests verify:

- the boundary is abstract and stateless;
- it is a subtype of `DecisionConstraintBoundary`;
- its `evaluate` signature exactly preserves the general contract;
- no grid facts or mutable state are stored;
- no production implementation or forbidden dependency is introduced;
- a test-only implementation preserves exact intent identity; and
- the public import works.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
