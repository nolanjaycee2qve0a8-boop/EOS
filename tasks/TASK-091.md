# TASK-091 — EMS Strategy Boundary

## Objective

Add only the abstract, stateless strategy evaluation boundary approved by ADR-087.

## Contract

```text
EMSContext
    |
    v
EMSStrategyBoundary.evaluate(context)
    |
    v
EMSDecision
```

`EMSStrategyBoundary` is abstract and empty-slotted. A conforming implementation accepts
exactly one `EMSContext` and returns exactly one `EMSDecision`.

The required provenance postcondition is:

```text
decision.source_context is context
```

Implementations must not mutate, copy, serialize, reconstruct, or retain the supplied
context. They signal failure by raising an exception.

## Statelessness

The boundary owns no mutable fields, cache, history, Runtime state, clock, scheduler,
device connection, command path, simulator, or constraint evaluator.

## Non-goals

- no Self Consumption, Zero Export, TOU, or MPC strategy;
- no optimization;
- no Constraint or Feasibility evaluation;
- no Battery model or Actuation handoff;
- no Runtime, Device, Command, Scheduler, or Simulator dependency;
- no modification to Phase 5–8 contracts or TASK-090 core artifacts.

## Validation

- abstract boundary cannot be instantiated;
- exact `evaluate(context: EMSContext) -> EMSDecision` signature;
- test-only minimal implementation can be instantiated;
- returned Decision preserves exact Context identity;
- boundary and test implementation have empty slots and no instance dictionary;
- production boundary has contract-only dependencies;
- full pytest, Ruff, and mypy validation.
