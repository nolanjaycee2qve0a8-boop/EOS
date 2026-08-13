# TASK-137 - Headroom-Aware MPC Cycle Integration

## Objective

Carry the complete TASK-136 headroom-aware optimization evidence through one
MPC cycle to a physical final solution, one control plan, one current action,
and one `EMSDecision`.

## Public contracts

- `HeadroomAwareMPCCycleResult`
- `HeadroomAwareMPCCycleBoundary`
- `HeadroomAwareSingleMPCCycleOrchestrator`

The cycle reuses `PhysicallyAwareMPCCycleInput`; its exact MPC facts, battery
state, and battery model are sufficient to construct the existing planning
artifacts without a second input contract.

## Execution shape

```text
PhysicallyAwareMPCCycleInput
    -> OptimizationProblem + BatteryOptimizationInput
    -> HeadroomAwarePhysicalOptimizationBoundary (once)
    -> physical final OptimizationSolution
    -> OptimizationControlPlan
    -> MPCCurrentAction
    -> EMSDecision
```

Only `headroom_optimization_output.physical_output.final_output.solution` is
eligible for plan construction. The original Net-Load candidate and the
headroom-adjusted pre-physical candidate remain evidence only and can never
directly produce the current decision.

## Compatibility view

`physical_cycle_view` is one `PhysicallyAwareMPCCycleResult` assembled from
the exact already-computed physical output, plan, action, and decision. It is
not a second execution path and does not invoke any domain boundary. Existing
TASK-123+ explanation infrastructure can therefore explain the headroom-
adjusted candidate to physical-final decision path unchanged, while the outer
result retains the additional original-candidate and headroom-reservation
evidence.

## Non-goals

No daily runner integration, horizon extension, explanation or CSV schema
change, headroom presentation formatting, repeated MPC loop, feasibility,
actuation, Simulator, runtime scheduler, or new optimization rule.
