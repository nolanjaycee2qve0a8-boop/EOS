# TASK-111 — Single MPC Cycle Orchestrator

## Objective

Implement one deterministic orchestration of existing MPC seams. One call
builds one optimization problem, solves it once, constructs one control plan,
extracts one current action, translates one `EMSDecision`, and stops.

## Architecture

```text
MPCCycleInput
    |
    v
SingleMPCCycleOrchestrator
    |
    +-> OptimizationBoundary.solve
    +-> OptimizationControlPlanConstructionBoundary.construct
    +-> MPCCurrentActionExtractionBoundary.extract
    +-> MPCDecisionTranslationBoundary.translate
    v
MPCCycleResult
```

All dependencies are caller supplied and held as immutable references. The
orchestrator creates `OptimizationProblem` only from exact facts already in
`MPCCycleInput`; it neither adds forecast data nor derives objectives.

## Execution semantics

For one successful call each dependency runs exactly once, in the shown order.
The first exception propagates unchanged; downstream seams are not invoked and
there is no retry. The result preserves the exact cycle input, Problem, Result,
plan, current action, and current decision identities.

## Non-goals

`SingleMPCCycleOrchestrator` is not a continuous MPC Runtime. It does not
repeat, schedule, refresh forecasts, advance time, mutate plans, execute future
steps, evaluate feasibility, hand off Actuation, or run the Simulator.

It introduces no solver, battery/SOC dynamics, physical clipping, Runtime,
Device, PCS, dispatch, or Command behavior.

## Validation

- frozen/slotted caller-injected dependency references;
- exact successful-cycle provenance and exactly-once invocation;
- stop-first exception propagation at every dependency stage;
- no Feasibility, Actuation, Simulator, Runtime, Device, or solver imports;
- full pytest, Ruff, mypy, and diff validation.
