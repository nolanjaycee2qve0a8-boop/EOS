# TASK-143 - Rolling Headroom-Aware MPC Cycle Integration

## Objective

Expose TASK-142's rolling-headroom physical-optimization composition through
one explicit MPC cycle. The existing TASK-137 full-horizon cycle remains
unchanged as its own truthful provenance path.

## Public contracts

- `RollingHeadroomAwareMPCCycleResult`
- `RollingHeadroomAwareMPCCycleBoundary`
- `RollingHeadroomAwareSingleMPCCycleOrchestrator`

## Execution shape

```text
full forecast
  -> TASK-142 rolling PV opportunity and selected horizon
  -> TASK-132 inner headroom requirement
  -> candidate planning
  -> explicit physical revision
  -> physical final OptimizationSolution
  -> OptimizationControlPlan
  -> MPCCurrentAction
  -> EMSDecision
```

The orchestrator invokes only the injected TASK-142 boundary. It does not
reach into opportunity selection, headroom accounting, candidate planning, or
physical revision directly.

## Provenance and compatibility

Only `physical_output.final_output.solution` can construct the control plan.
The candidate and reservation-adjusted candidate remain evidence, never an
execution source. The outer result also provides a `physical_cycle_view` that
reuses the exact physical output, plan, action, and decision, so the existing
MPC explanation chain remains compatible without a second optimization pass.

## Non-goals

No rolling-window formula changes, daily-runner/demo integration, solver,
forecast generation, repeated cycle, feasibility, actuation, simulator,
runtime, or device behavior is introduced.

## Validation

- focused rolling-MPC provenance and exactly-once tests
- full `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy .`
- `git diff --check`
