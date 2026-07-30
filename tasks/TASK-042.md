# TASK-042 - Constraint Composition Boundary

## Status

IN REVIEW

## Objective

Define how multiple existing `DecisionConstraintBoundary` implementations are
evaluated as one deterministic constraint chain.

TASK-042 composes constraints only. It introduces no optimization, strategy,
physical constraint rule, runtime integration, or device behavior.

## Architecture

~~~text
source DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        +--> Constraint 1
        |
        +--> Constraint 2
        |
        +--> Constraint N
        |
        v
final FeasibleDecisionIntent
~~~

## Public Contract

~~~python
ConstraintEvaluationPipeline.evaluate(
    source_intent: DecisionIntent,
    constraints: tuple[DecisionConstraintBoundary, ...],
) -> FeasibleDecisionIntent
~~~

The pipeline is stateless and uses empty slots. Constraint instances are
supplied by the caller for each invocation and are not retained.

## Ordering Contract

The tuple defines the complete evaluation order.

The pipeline:

- preserves exact caller order;
- does not sort;
- does not deduplicate;
- invokes every constraint at most once;
- passes each stage the exact inner `DecisionIntent` returned by the previous
  stage; and
- returns the exact `FeasibleDecisionIntent` returned by the final stage.

Policy does not select, inspect, or know the constraint order.

## Empty Composition

An empty constraint tuple is valid. The pipeline returns a new
`FeasibleDecisionIntent` wrapper whose inner intent is the exact source object:

~~~python
result.intent is source_intent
~~~

No synthetic constraint is introduced.

## Identity and Lineage

The source intent is never copied or mutated.

If all constraints preserve the supplied intent:

~~~python
result.intent is source_intent
~~~

If a constraint creates an adjusted immutable intent, the next constraint
receives that exact adjusted object. The final wrapper is returned without
copying or reconstruction.

TASK-039 source/feasible lineage remains unchanged. A future caller continues
to retain `DecisionContextResult.intent` as the source evidence while the
pipeline result supplies the final feasible evidence.

## Failure Contract

- Invalid inputs are rejected before any constraint runs.
- A constraint returning a non-`FeasibleDecisionIntent` raises `TypeError`.
- Constraint exceptions propagate unchanged.
- Evaluation stops immediately after a failure.
- No retry, rollback, partial result, cache, or history is introduced.

## Boundary Preservation

TASK-042 does not modify:

- `DecisionConstraintBoundary`;
- `DecisionIntent`;
- `FeasibleDecisionIntent`;
- battery or grid constraint contracts;
- policy or orchestration contracts;
- source/feasible lineage;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Non-goals

- Optimization, MPC, forecasting, scheduling, TOU, or pricing.
- Choosing the best constraint order.
- Combining constraint facts.
- Resolving conflicts between constraints.
- Parallel, async, threaded, or queued evaluation.
- Retry, rollback, or partial-failure semantics.
- Runtime, commands, dispatch, PCS/BMS, or device control.
- Persistence, telemetry, cache, or history.

## Tests

Focused tests cover:

- exact tuple ordering;
- exactly-once execution;
- exact previous-stage identity propagation;
- exact final wrapper identity;
- empty composition;
- no deduplication;
- source identity preservation;
- exception propagation and short-circuiting;
- invalid input and return types;
- empty slots and no retained state;
- dependency isolation; and
- public import.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
