# TASK-136 - Headroom-Aware Physical Optimization Composition

## Objective

Compose the existing TASK-132 PV headroom requirement, TASK-134 current-step
candidate planning, and TASK-135 explicit physical revision seams into one
explicit, deterministic optimization entry point.

## Public contracts

- `HeadroomAwarePhysicalOptimizationSolveOutput`
- `HeadroomAwarePhysicalOptimizationBoundary`
- `DeterministicHeadroomAwarePhysicalOptimizer`

## Composition

```text
PhysicallyAwareBaselineOptimizationInput
    -> PVHeadroomRequirement
    -> HeadroomAwareCandidatePlanningResult
    -> PhysicallyAwareOptimizationSolveOutput
```

The composition creates one exact `PVHeadroomRequirementInput` from the source
problem forecast, battery model, and explicit duration. It then creates one
candidate-planning input using that exact requirement and finally passes the
planner's exact `final_output` into one explicit physical revision.

## Provenance and execution semantics

The result retains the original physical input, calculated requirement,
candidate-planning result, and physical output. It requires:

- exact source forecast and battery-model identity in the requirement;
- exact battery input and requirement identity in candidate planning;
- `physical_output.source_input is source_input`;
- `physical_output.candidate_output is candidate_planning_result.final_output`.

Each injected dependency is invoked exactly once. The composition has no
candidate optimizer dependency; therefore it cannot re-solve the TASK-130
Net-Load candidate. Headroom reservation evidence remains separate from
`BatterySolutionRevisionReason`; physical revision reasons continue to describe
only physical power/SOC correction.

## Non-goals

No horizon extension, MPC integration, demo changes, simulator execution,
downstream feasibility/actuation, new physical rule, repeated correction, or
candidate optimizer behavior change.
