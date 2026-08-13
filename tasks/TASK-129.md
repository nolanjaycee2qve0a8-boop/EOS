# TASK-129 - Explainable MPC Daily Demo

## Objective

Provide `python -m ems_simulator.mpc_demo --output-dir simulation_output` as a
runnable deterministic demonstration of the completed TASK-128 finite daily
MPC integration.

## Demo chain

```text
Actual household day + 4-hour repeating perfect forecast
  -> 24 one-cycle physically-aware MPC evaluations
  -> physical revision and decision explanation
  -> downstream Feasibility/Handoff
  -> Simulator actual SOC progression
```

The CLI writes `mpc_decisions.csv`, `simulation_result.csv`,
`power_curve.svg`, `soc_curve.svg`, and `daily_summary.txt`.

## Forecast limitation

The demo caller constructs a separate four-point horizon for every hour. Near
the end of the day it repeats the household profile by `absolute_hour % 24`.
This is a deterministic perfect-forecast demonstration only: it is not a
forecast model, weather service, tariff prediction, or AI provider.

## Evidence distinction

`mpc_decisions.csv` explains the MPC decision request. It is not an execution
log. TASK-128 separately preserves the downstream feasible decision, actuation
handoff, and actual simulator trace. Projected planning SOC is likewise not
the actual next simulator SOC.

## Scope

The demo reuses existing TASK-128, physical optimizer, explanation, journal,
CSV, exporter, and simulator components. Its private adapters are the smallest
necessary implementations for frozen translation, feasibility, and handoff
boundaries; they introduce no new strategy, constraint, or physics behavior.

## Non-goals

No Runtime scheduler, clock, persistent forecast service, new optimization
objective, new feasibility policy, physical-model change, device/command work,
or change to the existing `ems_simulator.demo` CLI.
