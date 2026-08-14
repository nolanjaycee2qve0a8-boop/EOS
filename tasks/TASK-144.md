# TASK-144 - Rolling Headroom 24h Daily Runner Integration

## Objective

Add a parallel finite 24-hour application runner for the TASK-143 rolling
headroom MPC cycle. TASK-128 and TASK-138 remain frozen comparison paths.

## Public contracts

- `RollingHeadroomAwareExplainableMPCDailySimulationStepTrace`
- `RollingHeadroomAwareExplainableMPCDailySimulationResult`
- `RollingHeadroomAwareExplainableMPCDailySimulationBoundary`
- `RollingHeadroomAwareExplainableMPCDailySimulationRunner`

## Daily integration shape

For each of the 24 caller-owned forecast horizons, the runner creates one
`EMSContext`, one `PhysicallyAwareMPCCycleInput`, and invokes the injected
TASK-143 cycle exactly once. It then uses the outer cycle decision for
provenance, feasibility, handoff, and simulator execution.

```text
actual Simulator SOC/Grid feedback
  -> TASK-143 rolling MPC cycle
  -> exact physical_cycle_view
  -> existing explanation / journal / CSV contracts
  -> feasibility -> handoff -> Simulator
```

At hour zero planning state uses the daily initial SOC. Every subsequent hour
uses the previous Simulator `next_state.soc` and actual grid result; projected
or planned SOC/Grid values are never reused as realised state.

## Compatibility and evidence

`physical_cycle_view` is an exact read-only artifact from the outer rolling
cycle, not a second MPC run. Existing TASK-123+ explanation, journal and CSV
contracts receive this exact view unchanged. The CSV schema therefore remains
unchanged: detailed rolling-window facts stay in the outer cycle result.

## Failure behavior and non-goals

The runner is stop-first. CSV rows are serialized and written once only after
all 24 cycles complete; an earlier failure writes no partial decision CSV.

No demo CLI, forecast generation, rolling selection/formula/reservation logic,
explanation schema change, full-horizon runner modification, scheduling,
runtime, device integration, or optimisation rule is introduced.

## Validation

- 24-cycle provenance, actual state feedback, compatibility and exactly-once tests
- no-partial-CSV failure test
- full `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy .`
- `git diff --check`
