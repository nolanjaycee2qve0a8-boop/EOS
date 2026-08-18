# Residential EMS 1.0 — Campaign E: Probabilistic Forecast Robustness

## Scope and freeze boundary

Campaign E is post-freeze validation/reporting tooling. Residential EMS 1.0
remains in functional freeze. The campaign does not add or change Strategy,
optimizer, MPC, physical revision, Feasibility, Actuation, Simulator, runner,
ledger, comparison, acceptance, runtime, device, or command behavior.

It creates explicit caller-owned **synthetic forecast** facts, then reuses the
existing Campaign C frozen daily execution composition. Forecast facts are used
only for planning; the matching environment's realized PV/load/tariff facts
remain the only facts supplied to daily Simulator execution.

```powershell
python -m ems_simulator.residential_campaign_e --output-dir simulation_output_campaign_e
```

The output directory is deterministic generated evidence and remains
untracked.

## Exact matrix and execution accounting

| Item | Count |
| --- | ---: |
| Realized environments | 3 (Reference, High PV, High evening load) |
| Keyed synthetic samples per environment | 64 |
| Sampled scenarios | 192 |
| Fresh sampled Schedule/Economic paths | 384 |
| Independently executed perfect anchors | 6 |
| Actual 24-hour runner/Simulator executions | **390** |
| Sampled paired strategy comparisons | 192 |
| Sample-to-same-environment/strategy anchor regrets | 384 |

Each sampled Schedule/Economic pair receives the exact same immutable sampled
scenario and forecast horizons (common random numbers). The two strategies
are still fresh, independent daily executions. Perfect anchors are also fresh
executions and are read-only comparison references only; Campaign E verifies
their frozen Campaign A fingerprints.

## Synthetic forecast model

The fixed seed is `20260817`. Each random variate is a deterministic SHA-256
key of `(seed, environment, sample index, variable)`, so it is independent of
iteration order and uses no global random state or external package.

| Variable | Amplitude | Timing shift |
| --- | --- | --- |
| PV | triangular(-30%, 0, +30%) | -2,-1,0,+1,+2 h at 5/15/60/15/5% |
| Load | triangular(-25%, 0, +25%) | -2,-1,0,+1,+2 h at 5/15/60/15/5% |
| Import tariff | triangular(-20%, 0, +20%) | -1,0,+1 h at 15/70/15% |

Forecast values are `shift(realized) * (1 + amplitude)`, are nonnegative,
and source tuples are never mutated. PV zeroes remain zero under scaling; a
timing shift only moves existing profile values according to Campaign C's
established direction convention.

These are transparent engineering assumptions, not site-calibrated forecast
probabilities, a forecast model, or a production uncertainty model.

## Regret, statistics, and evidence

For each sampled path, `adjusted_cost_regret` is sampled adjusted net economic
cost minus the same environment/strategy perfect-anchor cost. Actual executed
battery-power divergence reads only:

`simulation_trace.state.battery_result.actual_power_kw`

It never substitutes planned power. Grouped `environment × strategy` rows
report regret, divergence-hour count, maximum actual-power difference, physical
revisions, and final actual SOC. Each group contains 64 samples and publishes
mean, population standard deviation, min, nearest-rank P05/P50/P90/P95/max and
positive/zero/negative counts where meaningful. These fractions describe this
fixed synthetic set, not real-world probabilities.

The output contains ten CSV/text artifacts, including sample fingerprints,
anchor results, path results, regret evidence, comparisons, separate sampled and
perfect-anchor hourly actual-power traces, acceptance findings, and distribution
summary. Eight XML-safe SVGs show
per-environment regret/divergence ECDFs plus physical-revision and ranking
summaries. Labels include seed, environment, strategy or explicit category.

The sample manifest retains three distinct evidence layers: stable source
realized PV/load/tariff fingerprints, the keyed amplitude/shift transformation
parameters, and SHA-256 fingerprints of the fixed-six-decimal normalized
forecast PV/load/tariff evidence representation. Each hourly value is emitted
in stable tuple order with an explicit comma delimiter and exactly six decimal
places; signed zero is canonicalized to `0.000000`. These fingerprints are not
hashes of raw Python binary floats: values that have the same six-decimal
representation intentionally have the same fingerprint. They establish report-
precision evidence identity only, and do not drive planning, control,
optimization, or numerical calculation. Its labelled combined forecast
fingerprint is the SHA-256 of
`pv:<fingerprint>|load:<fingerprint>|tariff:<fingerprint>` and supports
collision and Schedule/Economic-pair mapping review without changing any
forecast or control fact.

`campaign_e_hourly_trace.csv` is explicitly `execution_scope=sampled` and has
`384 × 24 = 9,216` rows. `campaign_e_anchor_hourly_trace.csv` is explicitly
`execution_scope=perfect_anchor` and has `6 × 24 = 144` rows. The latter is
derived only from the six already-retained anchor Simulator traces; it never
reruns anchors and neither trace is mixed into the sampled ECDF statistics.

## Interpretation and limits

Campaign E can expose how frozen control responds to a declared synthetic
forecast-error set. A passing result does not certify forecast-error robustness,
field reliability, weather accuracy, hardware safety, customer deployment
readiness, or probability of real outcomes. It does not optimize against a
distribution or change a control objective.

Campaign F should extend this work only with separately approved, transparent
correlation, extreme-combination, multi-day and forecast-source assumptions.
