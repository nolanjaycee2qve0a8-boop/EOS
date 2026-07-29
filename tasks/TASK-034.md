# TASK-034 ? Decision Evaluation Cycle Boundary

## Status

IN REVIEW

## Objective

Introduce `DecisionEvaluationCycle` as an immutable lifecycle observation over
the artifacts of one completed EMS decision evaluation.

The cycle validates existing artifact relationships. It does not execute a
policy, evaluate constraints, generate commands, or own runtime behavior.

## Architecture

~~~text
EnergySystemState
        |
        v
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextResult
        |
        v
DecisionIntent
        |
        v
FeasibleDecisionIntent
        |
        v
ConstraintExplanation
        |
        v
DecisionEvaluationCycle
~~~

## Contract

`DecisionEvaluationCycle` is a frozen, slotted dataclass containing exactly:

~~~python
context: DecisionContext
result: DecisionContextResult
source_intent: DecisionIntent
feasible_intent: FeasibleDecisionIntent
explanation: ConstraintExplanation
~~~

`create()` stores the exact supplied artifacts and derives `source_intent`
only by reading `result.intent`. It performs no copy, reconstruction,
serialization, normalization, or mutation.

## Lifecycle Validation

The cycle validates all relationships represented by current contracts:

~~~python
cycle.source_intent is cycle.result.intent
cycle.explanation.feasible_intent is cycle.feasible_intent
cycle.explanation.source_intent is cycle.source_intent
~~~

When no constraint adjustment occurs,
`cycle.feasible_intent.intent is cycle.source_intent`. When a constraint blocks
or clips the request, `cycle.feasible_intent.intent` is a different immutable
intent. Both relationships are valid lineage states.

`DecisionContextResult` does not retain its source `DecisionContext`, so the
cycle does not claim to independently prove that provenance. Re-running policy
evaluation to infer it would violate the observation-only boundary.

## Ownership

The cycle owns no policy, constraint implementation, runtime, dispatcher,
device, clock, storage, cache, or history. It cannot execute or progress any
artifact.

## Non-goals

- EMS algorithms or strategy calculation.
- Policy or constraint evaluation.
- Optimization, scheduling, or forecasting.
- Commands, events, dispatch, or device protocols.
- Runtime loops, progression, or state retention.
- Persistence, telemetry, cache, or history.
- Derived explanations, diagnosis, or recommendations.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
