# TASK-167 — Terminal Value Robustness Matrix

## Goal

TASK-167 evaluates whether the terminal-valuation break-even found in the single TASK-165/TASK-166 fixture remains explainable across several deterministic actual control outcomes. It is an observational/accounting matrix only: no economic gate, candidate, headroom schedule, MPC, Simulator, TASK-162 formula, or TASK-163 formula is changed.

## Fixed-control then accounting-only evaluation

Each scenario runs its existing Schedule-aware and Economic Schedule-aware daily paths once. Actual actions, SOC trajectories, grid energy, realized import cost, PV absorption, and throughput are fixed before any valuation sweep. Each matrix point then creates only one TASK-162 terminal-value evidence and one TASK-163 economic-outcome evidence per path.

```text
caller scenario -> fixed Schedule/Economic paths once
                                 ↓
                  valuation-price grid per scenario
                                 ↓
                 TASK-162 terminal value evidence
                                 ↓
                 TASK-163 net economic cost evidence
                                 ↓
                         ranking matrix
```

## Scenarios

- `R1_SMALL`: one `0.79` low-price grid-charge interval at `1.5 kW`.
- `R2_MEDIUM`: two `0.81` low-price grid-charge intervals at `1.5 kW`.
- `R3_LARGE_TASK165_BASELINE`: the frozen TASK-165 mechanism, with six `0.80` low-price intervals at `3.0 kW`.

All retain weak PV at or below load, a later maximum import price of `0.85`, and charge/discharge efficiency of `0.95 / 0.95`. The different terminal SOC outcomes arise through existing control semantics; no terminal SOC is set manually.

## Evidence and interpretation

For every scenario:

```text
delta_net_cost = Economic - Schedule
break_even_price = delta_realized_import_cost / delta_deliverable_terminal_energy
```

Negative net-cost delta means Economic is better; positive means Schedule-aware is better. The threshold is an accounting break-even under TASK-163, not a battery shadow price, market forecast, tariff recommendation, or optimized terminal coefficient.

TASK-166's original TASK-165 baseline is retained as `R3_LARGE_TASK165_BASELINE` and reproduces a break-even near `0.886427`. The matrix reports whether its other scenarios have the same or different thresholds, while explicitly decomposing the threshold into both realized-cost and deliverable-terminal-energy differences. Discharge efficiency is already included in TASK-162 deliverable energy and is never applied a second time.

## CLI outputs

```powershell
python -m ems_simulator.terminal_value_robustness_matrix `
  --output-dir simulation_output_task167_terminal_value_robustness
```

- `robustness_scenario_summary.csv`
- `terminal_value_robustness_matrix.csv`
- `evaluation_summary.txt`
- `break_even_price_by_scenario.svg`
- `terminal_soc_delta_by_scenario.svg`
- `realized_cost_vs_terminal_energy_delta.svg`
- `net_cost_delta_heatmap.svg`

The result remains observational. Even if terminal value is decision-relevant across the accounting matrix, this evidence alone does not authorize terminal value as a control objective.
