# TASK-108 — MPC Current Action Extraction Contract

## Objective

Define the explicit handoff from a proposed `OptimizationControlPlan` to one
current planned action and, separately, to one existing `EMSDecision`. This
task does not solve, execute, advance, or schedule the plan.

## Architecture

```text
OptimizationControlPlan
    |
    v
MPCCurrentAction extraction
    |
    v
one selected control step only
    |
    v
MPC decision translation
    |
    v
EMSDecision
    |
    v
Feasibility -> Actuation -> Simulator
```

## Contracts

`MPCCurrentAction` is frozen and slotted. It preserves exact identity to the
source `OptimizationControlPlan` and exactly one selected
`OptimizationControlStep`. The selected step must be an exact object in the
source plan; value-equal reconstructed and foreign steps are rejected.

`MPCCurrentActionExtractionBoundary` is an abstract empty-slotted seam. The
provided `FirstStepMPCCurrentActionExtractor` makes its rule explicit: it
selects only `plan.steps[0]` in caller order. Empty plans cannot yield a current
action. This rule is not clock matching, time advancement, or future-step
execution.

`MPCDecisionTranslationInput` preserves the selected current action and exact
caller-supplied MPC `EMSStrategyDescriptor`. The abstract
`MPCDecisionTranslationBoundary` translates that one action into the existing
`EMSDecision`, preserving the exact `EMSContext` reached through control-plan
provenance and the exact strategy descriptor identity.

## Responsibility separation

- `OptimizationControlPlan`: proposed future control sequence.
- `MPCCurrentAction`: one selected current planned action.
- `EMSDecision`: one current Strategy request.
- Feasibility: physical permission.
- Actuation: execution handoff.

Receding horizon means: solve a horizon, use the current action only, then
later solve again. TASK-108 implements neither repeated solving nor any loop.

## Non-goals

- no solver, MPC optimizer, solver invocation, or optimization loop;
- no clock, timer, scheduler, automatic progression, or future-plan execution;
- no SOC dynamics, Battery prediction, feasibility, clipping, or Actuation;
- no Simulator, runtime, device, PCS, dispatch, or command work;
- no changes to existing Context, Decision, Forecast, MPC, Optimization,
  Feasibility, Actuation, or Simulator contracts.

## Validation

- immutable/slotted exact plan and selected-step identity;
- reconstructed and foreign-step rejection;
- deterministic first-step selection and empty-plan rejection;
- exact Context, descriptor, semantic action, and power preservation during
  test-only decision translation;
- abstract/stateless boundaries and dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
