# TASK-043 - Constraint Explanation Chain Boundary

## Status

IN REVIEW

## Objective

Introduce an immutable observation boundary for the ordered explanations of an
already completed constraint evaluation chain.

TASK-043 records source/feasible identity, whether each stage adjusted its
input, and an explicit caller-supplied adjustment reason. It does not execute
constraints or derive reasons from physical state.

## Architecture

~~~text
source DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        v
final FeasibleDecisionIntent
        |
        v
ConstraintExplanationChain
        |
        +--> ConstraintExplanationEntry[0]
        |
        +--> ConstraintExplanationEntry[1]
        |
        v
ordered immutable explanation evidence
~~~

## ConstraintExplanationEntry

One entry observes one completed constraint stage:

~~~python
@dataclass(frozen=True, slots=True)
class ConstraintExplanationEntry:
    source_intent: DecisionIntent
    feasible_intent: FeasibleDecisionIntent
    adjusted: bool
    adjustment_reason: str | None
~~~

`source_intent` and `feasible_intent` are exact existing references.

The adjustment flag has one deterministic identity meaning:

~~~python
adjusted = feasible_intent.intent is not source_intent
~~~

The constructor validates this relationship. It does not compare values.

## Reason Contract

`adjustment_reason` is opaque evidence supplied by the caller.

- When `adjusted` is true, the reason must be a non-empty string.
- When `adjusted` is false, the reason must be `None`.
- The reason is not generated, normalized, interpreted, ranked, or analyzed.
- The entry does not inspect SOC, power limits, grid limits, prices, or device
  state to infer a reason.

TASK-043 is the separate architecture decision anticipated by ADR-032. The
existing `ConstraintExplanation` remains a two-reference relationship boundary
with no reason field.

## ConstraintExplanationChain

The chain observes ordered entries:

~~~python
@dataclass(frozen=True, slots=True)
class ConstraintExplanationChain:
    source_intent: DecisionIntent
    entries: tuple[ConstraintExplanationEntry, ...]
    feasible_intent: FeasibleDecisionIntent
~~~

The caller supplies the immutable tuple in completed evaluation order. The
chain preserves that exact tuple and does not sort, deduplicate, or rebuild
entries.

## Identity and Lineage

The chain validates identity with `is`:

1. The first entry's source is the chain source.
2. Every later entry's source is the exact previous entry feasible inner
   intent.
3. The chain final feasible wrapper is the exact final entry wrapper.
4. An empty chain requires its feasible inner intent to be the exact source
   intent.

The source/feasible lineage introduced by TASK-039 remains unchanged. The
chain adds observation evidence but does not replace cycle lineage.

## Observation-only Contract

Creation does not:

- invoke `ConstraintEvaluationPipeline`;
- invoke `DecisionConstraintBoundary.evaluate`;
- execute Policy;
- create or mutate a `DecisionIntent`;
- create or mutate a constraint result;
- modify `DecisionEvaluationCycle`; or
- retain runtime state.

## Boundary Preservation

TASK-043 does not modify:

- `DecisionIntent`;
- `DecisionConstraintBoundary`;
- `FeasibleDecisionIntent`;
- `ConstraintExplanation`;
- `ConstraintEvaluationPipeline`;
- `DecisionEvaluationCycle`;
- Policy contracts;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Non-goals

- Constraint algorithms or physical calculations.
- Derived reasoning, recommendation, diagnosis, or root-cause analysis.
- TOU, pricing, optimization, MPC, forecasting, or scheduling.
- Runtime, commands, dispatch, PCS/BMS, or device control.
- Persistence, telemetry, logging, cache, or history.
- Mutable explanation collections.

## Tests

Focused tests cover:

- exact entry source and feasible identities;
- adjusted identity semantics;
- explicit reason validation;
- frozen/slotted entry structure;
- exact tuple order and chain identity;
- unchanged and adjusted intermediate stages;
- empty chain identity;
- broken first, intermediate, and final identity rejection;
- tuple and member validation;
- observation-only dependencies;
- existing `ConstraintExplanation` stability; and
- public imports.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
