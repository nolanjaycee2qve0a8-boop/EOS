# TASK-115 - Solution-Aware Single MPC Cycle Integration

## Objective

Add a solution-aware one-cycle MPC path for optimizers that return both an
`OptimizationResult` and an `OptimizationSolution`, while retaining the
pre-existing generic result-only cycle unchanged.

## Architecture

```text
MPCCycleInput
    |
    v
SolutionAwareSingleMPCCycleOrchestrator
    |
    v
OptimizationProblem -> OptimizationSolveOutput -> OptimizationControlPlan
    |
    v
MPCCurrentAction -> EMSDecision
```

`MPCSolutionCycleResult` exposes every exact artifact: input, problem, solve
output, result, solution, control plan, current action, and decision. The full
chain is therefore inspectable without discarding solved-value provenance.

## Responsibility separation

- Generic cycle: `OptimizationBoundary` and result-only plan construction.
- Solution-aware cycle: `OptimizationSolutionBoundary` plus solution-aware
  plan construction.
- Both paths construct one plan, select one current action, emit one decision,
  and stop.

TASK-115 does not replace or alter the generic cycle. It performs no horizon
advance, forecast refresh, repeat solve, later-step execution, feasibility,
handoff, physical model, or simulation work.

## Empty solution behavior

An empty solution remains empty through control-plan construction. The existing
first-step extractor rejects it, and that failure propagates unchanged. The
orchestrator does not manufacture an idle action.

## Validation

- immutable/slotted result and abstract cycle boundary;
- exact result-and-solution provenance through to one decision;
- exactly-once calls and first-failure propagation;
- real price-aware optimizer + plan builder end-to-end charge/discharge tests;
- empty solution behavior and dependency-isolation checks.
