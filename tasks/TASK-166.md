# TASK-166 — Terminal Valuation Price Sensitivity Evaluation

## Goal

Evaluate the fixed TASK-165 terminal-SOC-divergence scenario across explicit terminal-energy valuation prices. This is post-run accounting evidence only: it does not change economic gating, candidate planning, the headroom schedule, MPC, Simulator execution, or the TASK-162/TASK-163 formulas.

## Frozen execution boundary

TASK-166 executes the existing TASK-165 Schedule-aware and Economic Schedule-aware daily paths once. Their actual battery actions, SOC trajectories, grid import/export, realized import cost, PV absorption, and throughput are then held fixed. Every sensitivity point only constructs TASK-162 `TerminalEnergyValueInput` / evidence and TASK-163 `EconomicOutcomeInput` / evidence for each path.

```text
fixed TASK-165 actual paths (once)
        ↓
terminal valuation price point
        ↓
TASK-162 TerminalEnergyValueEvidence (Schedule / Economic)
        ↓
TASK-163 EconomicOutcomeEvidence (Schedule / Economic)
        ↓
ranking evidence only
```

No sensitivity point reruns MPC, optimization, feasibility, actuation, or Simulator execution.

## Contracts

- `TerminalValuationBreakEvenEvidence` records Economic-minus-Schedule realized-cost and deliverable-terminal-energy deltas, plus the analytical threshold when its denominator is nonzero.
- `TerminalValuationSensitivityPoint` retains both exact terminal-value and outcome evidence objects at one valuation price.
- `TerminalValuationSensitivityResult` retains the exact TASK-165 result, ordered points, break-even evidence, and emitted artifact paths.
- `TerminalValuationRanking` follows `delta_net_economic_cost = Economic - Schedule`: negative means `economic_better`, positive means `schedule_better`, and tolerance-near zero means `break_even`.

The threshold is calculated, never hard-coded:

```text
break_even_terminal_valuation_price
  = delta_realized_import_cost / delta_deliverable_terminal_energy
```

## TASK-165 relationship and finding

TASK-165 showed that at valuation price `0.85`, terminal value shrinks the Economic path's realized-cost advantage from approximately `4.21` to `0.17`, because the Schedule-aware path retains more terminal energy.

TASK-166 maps the sign transition across the valuation-price grid. For the observed fixed evidence, the calculated break-even is approximately `0.886427` currency/kWh: below it Economic has lower limited net cost; above it Schedule-aware has lower limited net cost. This is an accounting threshold, not an optimized battery shadow price.

## CLI outputs

```powershell
python -m ems_simulator.terminal_valuation_sensitivity_demo `
  --output-dir simulation_output_task166_terminal_valuation_sensitivity
```

- `terminal_valuation_sensitivity.csv`
- `break_even_summary.txt`
- `evaluation_summary.txt`
- `net_economic_cost_vs_terminal_price.svg`
- `net_cost_delta_vs_terminal_price.svg`

The evaluator has deterministic output tests. Terminal value is clearly decision-relevant in this fixture, but TASK-166 keeps it observational. Sensitivity evidence alone does not justify integrating terminal value into control.
