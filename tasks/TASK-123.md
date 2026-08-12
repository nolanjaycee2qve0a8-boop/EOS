# TASK-123 - MPC Decision Explanation Read Model

## Objective

Provide a stable, machine-readable, immutable explanation of one selected
current action from one completed `PhysicallyAwareMPCCycleResult`. This is a
read model only: it organizes existing provenance and never changes a decision
or invokes optimization, projection, constraint evaluation, correction, or
execution.

## Mapping

The builder first finds the selected current action by exact identity in
`control_plan.steps`. It uses that exact index to retrieve the corresponding
final solution step, revision step, candidate solution step, and both
projection steps. It never guesses from timestamp, action, or numeric values.

## Evidence

The explanation retains exact candidate/final solution-step and revision-step
objects. It exposes the exact revision-reason tuple, separately ordered SOC and
power violation kinds for the selected step, original projection SOC values,
and final feasibility booleans read from final evaluation artifacts.

## Responsibility separation

```text
PhysicallyAwareMPCCycleResult
    -> MPCDecisionExplanation
    -> future formatter / log / API / UI / AI explanation
```

Explanation is not optimization, constraint evaluation, correction, execution,
or prose rendering. Formatting for humans is deliberately deferred.

## Non-goals

No horizon report, retry, solver, Simulator, Actuation, Runtime, Device,
Command, I/O, cache, persistence, or logging backend.
