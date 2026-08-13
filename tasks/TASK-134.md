# TASK-134 - Headroom-Aware Candidate Planning Boundary

## Objective

Compose one TASK-130 Net-Load candidate output with exact TASK-132 PV headroom
evidence and TASK-133 cheap-grid reservation evidence, without adding battery
state, battery model, or headroom facts to `OptimizationProblem`.

## Public contracts

- `HeadroomAwareCandidatePlanningInput`
- `HeadroomAwareCandidatePlanningResult`
- `HeadroomAwareCandidatePlanningBoundary`
- `DeterministicHeadroomAwareCandidatePlanner`

The input preserves an exact `BatteryOptimizationInput`, an exact
`PVHeadroomRequirement`, and an explicit duration. The requirement's battery
model must be the exact model referenced by the battery input.

## Candidate-to-final chain

```text
OptimizationProblem -> NetLoadAwareBaselineOptimizer -> source candidate output
BatteryOptimizationState + BatteryOptimizationModel + PVHeadroomRequirement
    -> TASK-133 reservation evidence (only when current step is cheap-grid charge)
source candidate output + optional reservation -> final candidate output
```

The source candidate output remains intact. The final output has a distinct
`OptimizationResult` and `OptimizationSolution`, while retaining the exact
source `OptimizationProblem` and timestamp identities.

## Current-step-only semantics

TASK-134 evaluates only the first/current candidate step. The supplied SOC is
the planning state at the beginning of the horizon; applying it independently
to future steps would invent a second SOC trajectory. Future candidate steps
therefore preserve their source Net-Load action and requested power exactly.

The reservation applies only when the current public forecast facts and public
TASK-130 configuration identify a low-price, no-PV-surplus grid-charge action.
PV-surplus charging is never restricted. Discharge and idle actions are also
unchanged.

## Exclusions

No `OptimizationProblem` change, no Net-Load rule change, no PV-headroom
recalculation, no future SOC scheduling, no physical revision, no feasibility,
no actuation, no Simulator, and no runtime scheduling.

## Validation

Focused tests prove low-price reservation, at-target idle conversion,
PV-surplus exemption, high-price/mid-price preservation, unchanged future
steps, unsupported-objective propagation, exact provenance, and dependency
isolation.
