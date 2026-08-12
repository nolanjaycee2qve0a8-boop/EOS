# TASK-122 - Physically-Aware MPC Cycle

## Objective

Integrate exactly one TASK-121 physically-aware optimization revision into one
MPC planning-to-decision cycle. The cycle ends at one `EMSDecision`; it neither
repeats, executes a plan, evaluates downstream strategy feasibility, nor invokes
Actuation or Simulator behavior.

## Flow

```text
MPC cycle facts + battery planning facts
    -> Physically-aware optimization
    -> Candidate evidence -> Revision -> Final evidence
    -> Final OptimizationSolution only
    -> OptimizationControlPlan -> CurrentAction -> EMSDecision
```

`PhysicallyAwareMPCCycleResult` keeps the exact
`PhysicallyAwareOptimizationSolveOutput` reference. Consequently the full
TASK-121 candidate, candidate evidence, revision, final solution, and final
evidence remain inspectable without copied or flattened artifacts.

## Key semantics

- The control-plan constructor receives only `final_output.solution`.
- Candidate solution values can never become the current decision directly.
- The MPC configuration is the sole source of control-step duration.
- Every injected dependency runs at most once; the first exception stops the
  cycle and propagates unchanged.
- Unsupported objectives remain unavailable and empty. The existing first-step
  extraction failure propagates; no idle action is fabricated.

## Non-goals

No repeated/receding-horizon loop, scheduler, timer, forecast refresh, state
advance, solver, new physical rule, strategy feasibility, Actuation, Simulator,
Runtime, Device, or Command work.
