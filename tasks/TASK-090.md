# TASK-090 — EMS Core Contracts

## Objective

Implement only the immutable core artifacts required by the Phase 9 EMS Strategy
Layer architecture frozen in ADR-087.

## Architecture

```text
DecisionContext + objective/capability evidence
        |
        v
EMSContext
        |
        v
future EMSStrategyBoundary
        |
        v
EMSDecision
```

TASK-090 adds no strategy boundary or strategy implementation. It defines the artifacts
that a future boundary will accept and return.

## Contracts

### EMSStrategyDescriptor

- frozen and slotted;
- immutable `name` and `version` identity;
- no implementation instance, cache, history, or Runtime state.

### EMSContext

- preserves the exact source `DecisionContext`;
- preserves exact objective/capability composition evidence;
- accepts only the exact active `CapabilityDescriptor` identity;
- performs no copying, normalization, execution, or state retention.

### EMSDecision

- preserves exact context, strategy descriptor, and semantic intent identities;
- stores a finite, non-negative raw requested power magnitude in kW;
- uses Phase 5 `DecisionIntent.action` for charge/discharge/idle direction;
- idle requires zero power; charge/discharge require positive power.

`EMSDecision` is not a feasible decision, `BatterySimulationActuation`, or `Command`.

## Non-goals

- no `EMSStrategyBoundary`;
- no Self Consumption, Zero Export, TOU, or MPC implementation;
- no Constraint or Feasibility evaluation;
- no Actuation handoff;
- no Simulator, Runtime, Device, Command, or Dispatcher dependency;
- no modification to Phase 5–8 contracts or Simulator behavior.

## Validation

- focused immutable contract tests;
- exact identity preservation and reconstructed descriptor rejection;
- invalid type, power, action/magnitude, and mutation rejection;
- public API and forbidden dependency checks;
- full pytest, Ruff, mypy, and pre-commit validation.
