# Residential EMS 1.0 - Simulation Validation Campaign B

## Scope and freeze boundary

Campaign B is post-freeze validation and reporting tooling. Residential EMS 1.0 remains in functional freeze: Campaign B does not change Strategy, MPC, headroom, economic planning, physical optimization, Feasibility, Actuation, or Simulator semantics. All forecasts are perfect, deterministic, caller supplied, and equal to the realized exogenous profiles. Export remains allowed and is settled at each explicit export tariff.

```powershell
python -m ems_simulator.residential_campaign_b --output-dir simulation_output_campaign_b
```

Outputs are untracked validation evidence.

## Exact matrix

Campaign B contains exactly 72 deterministic scenario records and 144 logical Schedule/Economic trajectory records.

| Group | Count | Explicit sweep |
|---|---:|---|
| B1 PCS | 18 | Symmetric charge/discharge limits 0.50, 0.75, 1.00, 1.50, 2.00, 3.00 kW x reference, high-evening-load, high-PV environments. |
| B2 initial SOC | 12 | 0.20, 0.25, 0.35, 0.50, 0.70, 0.90 x reference and high-evening-load environments. |
| B3 tariff opportunity | 18 | Six low/day/peak profiles x reference, high-evening-load, high-PV environments. |
| B4 accounting sensitivity | 24 | Explicit export-tariff/degradation/terminal-value combinations across E1 negative shift, terminal-SOC divergence, and high-PV reference. |

B4 deliberately is not a full Cartesian product. Its 24 cells cover zero, reference, export-credit, degradation-stress, terminal-credit and mixed-stress accounting reasons while remaining small enough for human review. B4 reuses the exact completed Schedule/Economic trajectory pair for each of its three source environments; it only rebuilds TASK-173 ledger and TASK-174 comparison evidence with explicit accounting inputs. Therefore there are 144 logical path records, but 102 unique actual control executions (B1-B3: 48 x 2; B4 sources: 3 x 2). No accounting sensitivity run may rerun control.

## Acceptance and interpretation

Every logical path is evaluated with the existing TASK-176 acceptance rules. Hard PASS means no BLOCKER and no MAJOR finding. Physical safety, actual Simulator feedback, ledger reconciliation, comparison reconciliation, provenance, and explanations remain hard evidence. A strategy loss, ranking flip, a non-monotonic trend, higher cost, or high revision count is an observed boundary condition for review, not an acceptance failure.

The report deliberately omits a planned-vs-executed-power gap KPI: existing outer provenance has path-specific physical planning evidence, but no common path-neutral Campaign KPI boundary exposes it without reconstruction. Actual Simulator execution remains the authoritative reported behavior.

## Outputs and handoff

The campaign emits scenario, path-KPI, comparison and findings CSVs; one CSV per matrix group; a summary; and eight deterministic SVGs for PCS, SOC, tariff, and accounting relationships. Each SVG draws the horizontal zero axis at its computed data zero baseline and renders deterministic rotated x labels that identify the swept input and environment. The B4 export-tariff, degradation-rate, and terminal-value charts each label their own accounting input together with scenario/environment traceability. The summary contains the hard status, severity counts, rankings, highest revisions, largest divergence and a human-review shortlist (failures, top revisions, top divergence, schedule wins, accounting ranking flips and final-SOC boundaries).

Campaign B is a physical/economic boundary sweep under perfect forecast. The next validation campaign should introduce caller-supplied forecast-error cases while retaining functional freeze and the same actual-Simulator/ledger/comparison reconciliation.
