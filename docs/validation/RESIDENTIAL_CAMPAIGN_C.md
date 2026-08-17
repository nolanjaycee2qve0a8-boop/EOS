# Residential EMS 1.0 - Simulation Validation Campaign C

## Scope

Campaign C is post-freeze validation/reporting tooling, not a new residential control-capability TASK. Residential EMS 1.0 remains in functional freeze. It does not modify Strategy, MPC, objectives, schedule/economic behavior, headroom, physical revision, Feasibility, Actuation, Simulator, ledger, comparison, or TASK-176 acceptance semantics.

```powershell
python -m ems_simulator.residential_campaign_c --output-dir simulation_output_campaign_c
```

The generated evidence is untracked.

## Existing-boundary composition

Campaign C uses two existing caller-owned boundaries without changing them:

`realized DailySimulationScenarioInput -> existing Simulator execution`

`separate ForecastHorizon tuple -> existing MPC planning`

The frozen daily runners consume the supplied horizon for each planning cycle, while their Simulator step creation continues to consume the realized daily input. Actual prior Simulator SOC and grid feedback remain authoritative. No planned value is substituted for execution, and no provenance is reconstructed.

## Exact deterministic matrix

Three realized environments are used: `REFERENCE` (A01), `HIGH_EVENING_LOAD` (A16), and `HIGH_PV` (A10). Each has exactly thirteen caller-supplied forecast cases: perfect, +/-25% PV, +/-25% load, PV/load/tariff earlier and later by two hours, optimistic combined, and pessimistic combined. This produces exactly 39 scenarios, two freshly executed frozen paths per scenario, and therefore 78 logical paths / 78 actual control executions. There are no accounting-only reuse cases.

Timing cases use explicit 24-hour circular displacement: “earlier by two” maps the realized value at `t+2` to forecast index `t`; “later by two” maps the realized value at `t-2` to forecast index `t`. No interpolation, normalization, or source mutation occurs.

## Evidence and limits

Forecast error is always `forecast - realized`. PV/load report signed daily energy bias, MAE and maximum absolute error; tariff reports signed mean bias, MAE and maximum absolute error. Every non-perfect execution is compared with the fresh same-environment/same-strategy perfect anchor for adjusted-cost regret and authoritative hour-by-hour actual battery-power divergence.

All paths retain existing TASK-173 ledger, TASK-174 comparison, and TASK-176 acceptance evidence. Positive regret, ranking changes, action divergence and SOC changes are observations for review, not new acceptance rules.

Campaign C is deterministic: it does not establish probability distributions, hardware robustness, PCS certification, field/customer readiness, controller tuning, or optimality. A probabilistic or multi-day forecast campaign requires a separately approved scope.
