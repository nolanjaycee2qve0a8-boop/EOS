# TASK-033 ? Decision Constraint Explanation Boundary

## Status

IN REVIEW

## Objective

Introduce `ConstraintExplanation` as an immutable observation boundary over an
existing `FeasibleDecisionIntent`.

TASK-033 preserves constraint evidence relationships. It does not derive,
recompute, diagnose, or recommend anything.

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

## Contract

`ConstraintExplanation` is a frozen, slotted dataclass containing exactly:

~~~python
feasible_intent: FeasibleDecisionIntent
source_intent: DecisionIntent
~~~

After the TASK-039 lineage refinement,
`ConstraintExplanation.create(feasible_intent, source_intent)` preserves:

~~~python
explanation.feasible_intent is feasible_intent
explanation.source_intent is source_intent
~~~

The feasible inner intent may be the same object as `source_intent` when no
adjustment occurred, or a different immutable object after a constraint
adjustment. Creation performs type validation and stores exact references. It
does not copy, reconstruct, serialize, normalize, execute, or mutate either
source object.

## Observation Only

The explanation boundary contains no reason text or derived analysis. It does
not call `DecisionConstraintBoundary.evaluate()` and has no knowledge of which
constraints were evaluated.

It contains no SOC data, power-limit calculation, device information, command,
event, dispatch state, optimization result, or forecast data.

## Non-goals

- Derived reasoning, diagnosis, or recommendations.
- Constraint algorithms or re-evaluation.
- SOC control, power clipping, or physical limit calculations.
- Commands, events, dispatch, or device protocols.
- Runtime, execution, persistence, or telemetry integration.
- Optimization or forecasting.
- Cache, history, or mutable state.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
