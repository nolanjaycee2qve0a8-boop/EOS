# TASK-092 — EMS Decision Provenance Contract

## Objective

Add an immutable observation artifact for the exact lineage of one completed
`EMSDecision` without changing the TASK-090 core contracts or TASK-091 boundary.

## Architecture

```text
EMSContext
    |
    v
EMSStrategyBoundary
    |
    v
EMSDecision
    |
    v
DecisionProvenance
```

## Contract

`DecisionProvenance` stores:

- the exact source `EMSContext`;
- the exact immutable `EMSStrategyDescriptor`;
- the exact `EMSDecision`.

It validates:

```text
provenance.decision.source_context is provenance.source_context
provenance.decision.source_strategy is provenance.source_strategy
```

Identity validation uses `is`. Value-equal reconstructed contexts and strategy
descriptors are rejected.

## Observation only

The artifact is frozen and slotted. It does not execute a Strategy, create or modify a
Decision, copy references, serialize/reconstruct lineage, evaluate constraints, call the
Simulator, retain history, or generate Commands.

## Non-goals

- no strategy logic or concrete strategy;
- no optimization;
- no Constraint or Feasibility evaluation;
- no Actuation handoff;
- no Simulator, Runtime, Device, or Command dependency;
- no modification to Phase 5–8 or TASK-090/091 contracts.

## Validation

- exact Context, Strategy descriptor, and Decision identity;
- reconstructed equal-object rejection;
- frozen/slotted and no instance dictionary;
- invalid reference type rejection;
- observation-only dependency inspection;
- full pytest, Ruff, mypy, and diff validation.
