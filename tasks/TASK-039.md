# TASK-039 - Decision Intent Lineage

## Status

IN REVIEW

## Objective

Refine the immutable decision evaluation lifecycle so it distinguishes the
original policy intent from the physically feasible intent produced by a
constraint.

TASK-038 introduced the first constraint that can block or clip an intent.
That made the earlier single-identity cycle contract invalid whenever the
constraint created a new immutable `DecisionIntent`.

## Architecture

~~~text
DecisionContextResult
        |
        v
source_intent
        |
        v
DecisionConstraintBoundary
        |
        v
FeasibleDecisionIntent
        |
        v
DecisionEvaluationCycle
~~~

## Lineage Contract

`DecisionEvaluationCycle` contains:

~~~python
context: DecisionContext
result: DecisionContextResult
source_intent: DecisionIntent
feasible_intent: FeasibleDecisionIntent
explanation: ConstraintExplanation
~~~

The policy source identity is mandatory:

~~~python
cycle.source_intent is cycle.result.intent
cycle.explanation.source_intent is cycle.source_intent
cycle.explanation.feasible_intent is cycle.feasible_intent
~~~

The feasible inner intent has two valid states:

~~~python
# No constraint adjustment
cycle.feasible_intent.intent is cycle.source_intent

# Constraint blocked or clipped the request
cycle.feasible_intent.intent is not cycle.source_intent
~~~

In both cases, every stored object is the exact existing immutable artifact.
The cycle performs no copying, reconstruction, serialization, mutation, policy
evaluation, or constraint evaluation.

## Constraint Explanation

`ConstraintExplanation.create(feasible_intent, source_intent)` receives both
completed artifacts explicitly. It preserves the exact policy source intent
and exact feasible wrapper without deriving reasons or recalculating the
constraint.

## Compatibility Boundaries

TASK-039 does not modify:

- `DecisionIntent`;
- `DecisionContextPolicy` or concrete policy behavior;
- `DecisionConstraintBoundary` or its `evaluate(intent)` signature;
- `BatteryConstraintImplementation` rules;
- legacy `EMSPolicy` or legacy `DecisionResult`; or
- runtime and execution paths.

The removed `DecisionEvaluationCycle.intent` field has no compatibility alias.
The public lifecycle contract exposes `source_intent` instead.

## Tests

Focused tests cover:

- unchanged feasible intent identity;
- successful cycle creation after battery power clipping;
- exact policy source lineage;
- exact feasible output lineage;
- immutable, frozen, slotted cycle structure; and
- stateless orchestration through existing boundaries.

## Non-goals

- New EMS policies or strategy changes.
- New constraint rules, SOC calculation, or battery modeling.
- Commands, dispatch, PCS/BMS control, or device protocols.
- Runtime or execution changes.
- Persistence, telemetry, optimization, or forecasting.
- Mutable history, cache, or state retention.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
