# TASK-135 - Explicit Candidate Physical Revision Seam

## Objective

Allow an already-created `OptimizationSolveOutput` to enter the existing
candidate-to-evidence-to-revision physical flow without solving a new candidate
or duplicating the TASK-121 physical revision algorithm.

## Public contracts

- `ExplicitCandidatePhysicalRevisionInput`
- `ExplicitCandidatePhysicalRevisionBoundary`
- `DeterministicExplicitCandidatePhysicalReviser`

The wrapper input validates that its candidate result references the exact
`OptimizationProblem` held by `PhysicallyAwareBaselineOptimizationInput`, and
that the candidate solution references that exact candidate result.

## Shared revision seam

```text
candidate OptimizationSolveOutput
    + PhysicallyAwareBaselineOptimizationInput
    -> DeterministicExplicitCandidatePhysicalReviser
    -> PhysicallyAwareOptimizationSolveOutput
```

`PhysicallyAwareBaselineOptimizer` remains backward-compatible as a
convenience composer: it calls its `OptimizationSolutionBoundary` exactly once,
then delegates the returned exact output through this explicit seam. There is
one implementation of candidate projection, SOC/power evaluation, aggregate,
sequential one-pass revision, and final evidence evaluation.

## Provenance and scope

The output's `source_input` remains the exact nested
`PhysicallyAwareBaselineOptimizationInput`, while `candidate_output` is the
exact precomputed object supplied to the wrapper. A distinct final result and
solution are still created for the revised candidate and retain the exact
source problem.

TASK-134 can now pass its `final_output` directly to physical revision. The
physical layer receives only an explicit candidate plus battery physical facts;
it has no headroom, PV reservation, price, Net-Load, Simulator, feasibility,
or actuation dependency.

## Non-goals

No MPC integration, headroom-aware demo, horizon extension, physical rule
change, candidate re-solve, repeated correction, feasibility, actuation, or
Simulator behavior.
