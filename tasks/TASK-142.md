# TASK-142 - Rolling Headroom-Aware Physical Optimization Composition

## Objective

Add a parallel physical-optimization composition that uses TASK-141 rolling PV
opportunity headroom evidence. The existing TASK-136 full-horizon path remains
unchanged because its output truthfully requires the inner headroom requirement
to retain the exact full optimization forecast horizon.

## Public contracts

- `RollingHeadroomAwarePhysicalOptimizationSolveOutput`
- `RollingHeadroomAwarePhysicalOptimizationBoundary`
- `DeterministicRollingHeadroomAwarePhysicalOptimizer`

The deterministic composer receives a caller-owned
`PVOpportunityWindowConfiguration`, a TASK-141
`RollingPVHeadroomRequirementBoundary`, the TASK-134 candidate planner, and
the TASK-135 explicit physical reviser.

## Parallel provenance path

```text
full OptimizationProblem ForecastHorizon
  -> TASK-141 rolling opportunity window
  -> new selected ForecastHorizon (exact selected ForecastPoint references)
  -> TASK-132 PVHeadroomRequirement
  -> TASK-134 HeadroomAwareCandidatePlanningResult
  -> TASK-135 PhysicallyAwareOptimizationSolveOutput
```

The outer result retains each stage. It requires the rolling input to reference
the exact full problem horizon, but correctly requires the inner TASK-132
headroom input to reference the exact new selected horizon instead.

## Execution and identity guarantees

- injected window configuration is retained by exact identity in the rolling
  evidence
- the rolling headroom calculator executes once
- candidate planning executes once and receives the exact inner headroom
  requirement
- physical revision executes once and receives the exact planner `final_output`
- `physical_output.candidate_output is candidate_planning_result.final_output`

TASK-142 does not reconstruct window, forecast points, selected horizon, or
headroom evidence. TASK-140 owns PV opportunity and cloud-gap semantics;
TASK-132 owns energy, efficiency, charge-power cap, and usable-SOC-window
formula semantics.

## Behavior boundaries

The composition preserves first-opportunity-only behavior, current-opportunity
behavior, retained confirmed cloud gaps, and the empty-opportunity behavior
from TASK-141. Empty rolling headroom means TASK-132 emits zero headroom and
the existing TASK-133/134 candidate/reservation behavior continues normally.

No MPC cycle, daily runner, demo, reservation algorithm, candidate algorithm,
physical algorithm, simulator, feasibility, actuation, runtime, or scheduling
behavior is changed. TASK-139 therefore remains at its existing measured
baseline until a later explicit integration task consumes this parallel path.

## Validation

- focused provenance and exactly-once composition tests
- full `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy .`
- `git diff --check`
