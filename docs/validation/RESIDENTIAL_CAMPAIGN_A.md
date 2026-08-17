# Residential EMS 1.0 — Simulation Validation Campaign A

## Scope

Campaign A is the first post-freeze validation gate for Residential EMS 1.0.
It runs the frozen Schedule-aware and Economic Schedule-aware paths only. It
adds campaign scenario definitions, aggregation, reporting and tests; it does
not alter Strategy, MPC, headroom, economic planning, physical revision,
feasibility, handoff, or Simulator behaviour.

Forecast is perfect and caller-supplied: it equals each realized exogenous PV,
load and import-tariff trajectory. Export is explicitly allowed and settled at
the scenario's explicit export tariff; zero-export is not enabled.

```powershell
python -m ems_simulator.residential_campaign_a --output-dir simulation_output_campaign_a
```

Outputs are validation evidence and remain untracked.

## Execution and acceptance

Each scenario runs each primary path exactly once:

`caller facts -> frozen MPC path -> actual Simulator trajectory -> TASK-173 ledger -> TASK-174 comparison -> TASK-176 acceptance`

Accounting and reporting use already-completed trajectories and do not rerun
control. A hard PASS requires zero TASK-176 BLOCKER findings and zero TASK-176
MAJOR findings. An Economic loss, higher import/export, throughput change or
ranking reversal is an experimental observation, not an acceptance failure.

This is readiness for a planned simulation campaign only—not PCS control,
field safety, real-weather robustness, hardware integration or deployment.

## Exact deterministic matrix

Every profile has 24 one-hour values. `campaign_scenarios.csv` records every
final load, PV, import-tariff, battery, accounting and candidate-configuration
value without hidden defaults. The base is TASK-175: 10 kWh, SOC range
20%–100%, 3 kW charge/discharge, efficiencies 0.95/0.95, initial SOC 0.50,
TOU `0.20 x6, 0.50 x12, 0.90 x4, 0.50 x2`, export tariff 0.20, degradation
0.05, terminal valuation 0.85, and candidate thresholds 0.30/0.80 with 3 kW
requested grid charge.

| IDs | Exact variation |
|---|---|
| A01 | TASK-175 frozen reference semantics. |
| A02 | TASK-172 E1: `0.80 x6, 0.85 x18`; thresholds 0.80/1.00. |
| A03 | TASK-165: A02 facts with every PV value capped at 0.60 kW. |
| A04–A07 | Initial SOC 0.20, 0.35, 0.70, 0.90. |
| A08–A10 | PV zero; PV ×0.50; PV ×1.50. |
| A11 | PV at 12:00–16:00 = 0.05, 0.10, 0.45, 0.50, 0.40 kW. |
| A12 | PV at 08:00–17:00 = 2.4, 3.0, 2.2, 0, 0, 0, 2.0, 2.8, 2.2, 1.6 kW. |
| A13–A14 | Load ×0.70; load ×1.30. |
| A15 | Load +1.50 kW at 06:00–09:00. |
| A16 | Load +1.80 kW at 18:00–21:00. |
| A17 | Load +1.20 kW at 08:00–17:00. |
| A18 | Flat import tariff 0.50. |
| A19 | Weak TOU `0.45 x6, 0.50 x12, 0.55 x4, 0.50 x2`. |
| A20 | Strong TOU `0.10 x6, 0.50 x12, 1.20 x4, 0.50 x2`. |
| A21–A22 | Export tariff 0.60; export tariff 0.00. |
| A23 | Charge/discharge PCS power both 1.50 kW. |
| A24 | Degradation rate 0.15 per kWh throughput. |

## Reporting and review

The campaign emits scenario, KPI, comparison and finding CSVs; a summary; and
five compact SVGs. All CSV/report ordering is deterministic. The anomaly
shortlist uses explicit thresholds: any BLOCKER/MAJOR, Economic loss > 0.25,
absolute cost divergence > 0.50, throughput > 1.5× campaign median, or
physical revisions > campaign median + 2.
