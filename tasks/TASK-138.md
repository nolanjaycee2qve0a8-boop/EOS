# TASK-138 - Headroom-Aware Explainable Daily Simulation Integration

## Objective

Add a separate finite 24-step application integration for TASK-137
`HeadroomAwareMPCCycleBoundary`. The frozen physical daily runner remains
unchanged.

## Public contracts

- `HeadroomAwareExplainableMPCDailySimulationStepTrace`
- `HeadroomAwareExplainableMPCDailySimulationResult`
- `HeadroomAwareExplainableMPCDailySimulationBoundary`
- `HeadroomAwareExplainableMPCDailySimulationRunner`

The existing `ExplainableMPCDailySimulationInput` is reused exactly, including
the caller-owned 24-horizon tuple, configuration, battery model, locale, and
CSV path.

## Per-hour flow

```text
actual simulator SOC + grid result
    -> HeadroomAwareMPCCycleResult
    -> physical_cycle_view
    -> existing explanation / journal / CSV contracts
    -> outer exact EMSDecision
    -> Feasibility -> Handoff -> Simulator
```

Each trace retains both the outer `HeadroomAwareMPCCycleResult` and its exact
`physical_cycle_view`. The view is used only where stable explanation, journal,
and CSV contracts require `PhysicallyAwareMPCCycleResult`; it is never rebuilt.
The outer result retains the richer original candidate, headroom requirement,
reservation, and headroom-adjusted candidate provenance.

## State and failure semantics

The first cycle receives the caller's initial SOC. Every subsequent cycle uses
the actual previous simulator next-SOC and grid result, not projected planning
SOC or forecast grid values. The runner stops on the first failure and only
serializes/writes the decision CSV after all 24 steps succeed.

## Limitations

The existing physical CSV continues to explain headroom-adjusted candidate to
physical final decision. It intentionally does not add headroom-specific
columns. Caller-owned forecast horizon length is unchanged; this task does not
make midnight automatically see midday PV.

## Non-goals

No daily demo/CLI, horizon extension, forecast generation, optimizer change,
headroom explanation formatting, CSV schema change, scheduler, zero-export,
or new physical behavior.
