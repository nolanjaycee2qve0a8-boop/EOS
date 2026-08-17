# Residential EMS 1.0 — Simulation Validation Campaign D

## Scope

Campaign D is post-freeze validation and reporting tooling. Residential EMS 1.0
remains in functional freeze. The campaign composes existing frozen daily
Schedule-aware and Economic Schedule-aware runners; it does not add a
multi-day controller or alter Strategy, optimizer, MPC, physical revision,
Feasibility, Actuation, Simulator, ledger, or acceptance behavior.

```powershell
python -m ems_simulator.residential_campaign_d --output-dir simulation_output_campaign_d
```

Generated evidence is deterministic and remains untracked.

## Exact matrix and execution accounting

Campaign D owns six explicit multi-day sequences:

| Case | Sequence | Days |
| --- | --- | ---: |
| D01 | A01 × 7 | 7 |
| D02 | A16 × 7 | 7 |
| D03 | A10 × 7 | 7 |
| D04 | A01, A01, A10, A01, A16, A16, A10 | 7 |
| D05 | D04 × 4, A01, A01 | 30 |
| D06 | A10 × 10, A16 × 10, A01 × 10 | 30 |

The matrix contains exactly 88 scenario-days. Each day runs a fresh frozen
daily path for Schedule and Economic: 176 actual 24-hour executions, 12
logical multi-day paths, six comparison records, no accounting-only paths and
no trajectory reuse.

## Continuity and forecast semantics

Schedule and Economic retain separate actual SOC chains. Day zero receives the
case initial SOC. Each later daily input receives only the previous completed
Simulator `next_state.soc` from its own strategy chain. The next day begins
exactly one hour after the prior day’s final hourly trace. Battery-model,
strategy-descriptor and export-policy continuity are checked explicitly.

Every day keeps the frozen perfect-forecast semantics: its caller-owned
forecast horizon is built from the same day’s realized profile. Campaign D
does not claim multi-day forecast uncertainty, restart recovery, real-time
scheduling, or global multi-day optimality.

## Multi-day accounting

Daily TASK-173 ledgers remain intact as diagnostics. Campaign D separately
reconciles all daily realized import cost, export revenue and degradation cost.
It calculates TASK-162 terminal energy value exactly once from the final actual
SOC and final-day caller-supplied terminal valuation, then performs one
TASK-168 aggregate outcome calculation:

`aggregate adjusted cost = import cost - export revenue + degradation - final terminal value`

Daily terminal values are never summed into the multi-day terminal asset.

## Output evidence

The generated evidence includes the six case definitions, 88 scenario-day fact
rows, 176 day-path results, carry continuity, multi-day summaries, aggregate
comparisons, findings, a text summary, and deterministic SOC/cost/grid/revision
SVGs. This validates continuity and accounting reconciliation only; it is not
hardware, field, customer, or financial-deployment readiness evidence.
