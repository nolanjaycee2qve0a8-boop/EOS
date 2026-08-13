# TASK-130A - Generalize Physically-Aware Candidate Optimizer

## Objective

Remove the concrete dependency between the battery physical revision path and
`PriceAwareBaselineOptimizer`. The revision path now accepts any exact
`OptimizationSolutionBoundary` candidate producer.

## Before and after

```text
Before
PriceAwareBaselineOptimizer
    -> PhysicallyAwarePriceBaselineOptimizer

After
OptimizationSolutionBoundary
    -> PhysicallyAwareBaselineOptimizer
```

`PhysicallyAwarePriceBaselineOptimizer` remains a compatibility alias for the
existing price-baseline entry point. The underlying physical revision is no
longer price-specific.

## Preserved semantics

- Candidate output and all candidate physical evidence remain exact artifacts.
- One deterministic candidate-to-final revision pass remains unchanged.
- Final SOC/power evidence and `BatterySolutionRevision` remain unchanged.
- No retry, Solver, Simulator, downstream strategy feasibility, Actuation, or
  device behavior is introduced.

## Boundary rule

The candidate producer must be an `OptimizationSolutionBoundary`; it is called
exactly once with the exact input `OptimizationProblem`. Its result must retain
that exact problem identity and its solution must retain the exact result
identity. Invalid provenance fails explicitly.

## Acceptance evidence

Focused tests include a non-price `OptimizationSolutionBoundary` fake. It
produces a deterministic candidate and proves that the generalized physical
revision retains candidate provenance while applying existing power and SOC
revision semantics.

## Non-goals

This task does not add Net-Load-Aware optimization, PV/load rules, grid
constraints, zero-export behavior, new objectives, or any physical revision
algorithm change.
