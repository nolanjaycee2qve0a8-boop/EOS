# TASK-100 — Strategy Coordinator

## Objective

Add a narrow, immutable coordination boundary for multiple caller-supplied
Phase 9 EMS strategies. It evaluates every supplied strategy once and returns
the exact `EMSDecision` selected by caller-supplied descriptor priority.

## Architecture

```text
caller-supplied EMSStrategyBoundary tuple
    |
    v
StrategyCoordinator
    |
    v
exact selected EMSDecision
```

`StrategyCoordinatorConfiguration` owns only an ordered tuple of exact
`EMSStrategyDescriptor` references. The strategy tuple and priority tuple are
both caller supplied, retained without normalization, and use identity checks.

## Execution and provenance contract

- Every strategy is evaluated exactly once in the caller-supplied strategy
  tuple order.
- Selection uses the caller-supplied `strategy_priority` descriptor order; no
  ranking, score, weight, or inferred priority exists.
- The return value is the exact `EMSDecision` produced by the selected strategy:
  it is not copied, wrapped, or reconstructed.
- Consequently, `decision.source_context is context` and
  `decision.source_strategy is selected_strategy.descriptor` remain true.
- `DecisionProvenance` remains a separate caller-owned evidence artifact. The
  coordinator creates no new provenance artifact and preserves the selected
  decision reference that such evidence observes.

## Non-goals

- no optimization, objective weighting, MPC, forecasting, or feasibility;
- no SOC handling, battery control, physical model execution, or clipping;
- no command generation, runtime state, history, cache, device access, or
  simulator integration;
- no modification to existing strategy, feasibility, handoff, or simulator
  contracts.

## Validation

- frozen/slotted tuple-only configuration and frozen/slotted coordinator;
- exact descriptor identity coverage and reconstructed-descriptor rejection;
- caller-order exactly-once strategy evaluation and priority selection;
- selected decision, context, strategy descriptor, and provenance identity;
- full pytest, Ruff, mypy, and diff validation.
