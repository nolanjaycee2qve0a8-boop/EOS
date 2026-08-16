# TASK-172 — Extended Economic Scenario Re-evaluation

## Goal

TASK-172 is an observational re-evaluation of existing Schedule-aware and
Economic Schedule-aware trajectories. It combines the already-frozen TASK-168
extended accounting chain without changing any candidate, optimization, MPC,
feasibility, actuation, or simulator behaviour.

## Fixed-control composition

The module reuses TASK-161 E0/E1/E2 and TASK-165 terminal-SOC-divergence
paths. Each source runner executes once. Only after every actual daily trace is
complete does TASK-172 attach accounting sensitivities; export tariff,
degradation rate, and terminal valuation never re-run control.

```text
fixed completed trajectory
  -> realized interval import cost (existing source settlement)
  -> TASK-169 ExportRevenueEvidence
  -> TASK-170 BatteryDegradationCostEvidence
  -> TASK-162 TerminalEnergyValueEvidence
  -> TASK-168 ExtendedEconomicOutcomeEvidence
```

The frozen final aggregation remains exclusively TASK-168:

```text
adjusted_net_economic_cost =
    realized_import_cost
    - realized_export_revenue
    + battery_degradation_cost
    - terminal_energy_value
```

Lower is better under this limited accounting model; it is not cash profit.

## Accounting assumptions

The deterministic matrix uses export tariffs `0.20` and `0.60`, throughput
degradation rates `0.00`, `0.05`, and `0.10`, and terminal valuation prices
`0.00`, `0.60`, `0.85`, `0.886427`, and `0.90` currency/kWh. Throughput is exactly the
existing `DailyMetrics.battery_throughput_kwh` basis: the daily runner's
`sum(abs(actual battery power) * step duration)`.

TASK-171 remains a correct scalar import-settlement evidence boundary. The
reused scenarios have time-varying import tariffs, so TASK-172 deliberately
retains their existing coherent interval-realized import cost rather than
substituting a fabricated average scalar tariff. TASK-171 is covered through a
constant-tariff compatibility check and is not called to settle those TOU paths.

## Output

`python -m ems_simulator.extended_economic_re_evaluation --output-dir
simulation_output_task172_extended_economic` writes scenario/matrix CSVs, a
plain-language summary, and deterministic component/sensitivity SVGs. The
generated output directory is not source-controlled.
