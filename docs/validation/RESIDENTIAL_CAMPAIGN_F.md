# Residential EMS 1.0 Campaign F

Campaign F is post-freeze validation/reporting orchestration for correlated and
tail multi-day robustness. It changes no residential control capability.

Campaign E is merged on base `bec48ce`. Campaign F is currently a local-only,
pre-publication validation commit on
`campaign/residential-phase-f-correlated-tail-robustness`: it has not been
pushed, has no PR and is not merged. Its result is not production robustness,
hardware, PCS, BMS, DSP, HIL, field or customer-readiness certification.

## Real execution chain

`scenario-day forecast -> ForecastHorizon -> frozen daily runner -> Simulator
actual trace -> same-Strategy SOC carry -> multi-day ledger -> anchor regret ->
core/tail evidence`

The three exact realized seven-day sources are Campaign D
`D01_7D_REFERENCE_REPEAT`, `D03_7D_HIGH_PV_REPEAT`, and
`D02_7D_EVENING_REPEAT`. Case IDs, exact source scenario sequence, initial
SOC, timestamp and source-profile fingerprint are retained; there is no generic
reference-day fallback. For every scenario-day, transformed caller-owned
PV/load/tariff tuples enter the planning `ForecastHorizon`, while the source
facts alone enter `DailySimulationScenarioInput` and Simulator execution.

## Matrix and sampling

- 48 keyed correlated core scenarios and 12 deterministic tail scenarios;
  60 scenarios and 420 immutable scenario-days.
- 120 sampled/tail Schedule/Economic multi-day paths, six perfect anchors and
  126 independent paths total.
- 840 sampled/tail plus 42 anchor frozen daily executions: 882 total.
- 756 same-Strategy actual-SOC boundaries, 20,160 sampled/tail trace hours,
  1,008 anchor trace hours.

Core seed is `20260818`. PV/load/tariff innovations use the fixed correlation
matrix and its checked Cholesky lower factor, SHA-256 keyed open-interval
Box--Muller normals, and daily AR(1) amplitude `rho=0.70`. Timing has an
independent keyed AR(1) latent `rho=0.65`. The day manifest retains independent
and correlated innovations, prior/current latents, unclipped/clipped errors,
clip flags, shifts, and forecast/realized fingerprints. Core clips are PV
`[-0.40,+0.40]`, load `[-0.35,+0.35]`, tariff `[-0.30,+0.30]`.

The four tail cases are unweighted deterministic stress cases: optimistic
energy, pessimistic energy, timing dislocation, and a day-index-3 regime
reversal. They are not core clips and never enter core mean/stddev/percentile or
ECDF evidence.

## Accounting, results and output contract

Schedule and Economic execute independently, each using only its own prior
Simulator final SOC. Daily realized flow accounting is summed, and terminal
value is credited once from day seven's actual SOC. Each sample/tail path is
compared only with the same-regime/same-Strategy perfect anchor. Actual-power
divergence reads `simulation_trace.state.battery_result.actual_power_kw`.

Run:

```powershell
python -m ems_simulator.residential_campaign_f --output-dir simulation_output_campaign_f
```

The deterministic untracked output topology is 16 root CSV/TXT files, 10 root
SVGs and 882 nested daily `mpc_decisions.csv` files: 908 recursive files.
Publication is a four-stage state machine: semantic validation, non-final
artifact validation, finalization, then final-artifact validation. `PASS` is
emitted only after the final summary/findings, root topology, every nested CSV
and every SVG have passed the final contract. The final summary is an exact,
ordered schema: fixed campaign/count/execution/metric/gate fields have no
unknown, duplicate, missing, empty or reordered keys, and each value is checked
against the completed in-memory result and the final artifact count. Each of
the maximum-regret, maximum actual-power-difference and maximum-revision
metrics is an argmax evidence *set*, not one representative object: summary
records the scalar value, a deterministic JSON array of every
`scenario_id`/`strategy`/`value` reference and its count. Floating membership
uses absolute tolerance `1e-9` and relative tolerance `0`; integer revisions
use exact equality. References sort by scenario ID then canonical strategy
order Schedule/Economic. The validator parses the arrays with `json.loads` and
independently recomputes the complete retained argmax set directly from raw
retained regrets and path summaries. It shares only frozen strategy/tolerance/
schema constants with generation: it does not call generation's maximum, tie
collection, ordering or JSON serializer helpers. It rejects an omitted, extra,
duplicate, non-maximum or malformed reference. In the frozen normal result all
three maxima are Schedule/Economic ties: regret
`F-HIGH_EVENING_LOAD-F-TAIL-03`, power `F-REFERENCE-F-TAIL-03`, and revisions
`F-HIGH_EVENING_LOAD-CORE-05`.

Generator-side regression injects omission of either strategy, reversed order,
wrong scenario identity, an extra non-maximum reference, a wrong count and
malformed serialized JSON. All seven are fast targeted independent-validator
regressions with zero nested scans; they prove local detection only. Omit
Schedule, wrong scenario, extra non-maximum, wrong count and malformed JSON
also each traverse the real `main()` final publication flow: the production
gate scans all 882 nested CSVs, emits `OUTPUT_CONTRACT_FAILURE`, writes a
parseable diagnostic hard/publication `FAIL`, and exits nonzero. Tests do not
manually construct a finding or final status for those integration cases.

Each of the 882 nested `mpc_decisions.csv` artifacts is parsed with the standard
CSV parser and checked for the exact 24-column public schema, exactly 24 data
rows, an explicit one-hour timezone-aware timestamp sequence, finite numeric
fields, semantic action/boolean fields, and exact row-by-row equality with its
retained completed daily trajectory. Regression covers first/middle/last record
deletion and duplication, reordered records, non-first strategy/timestamp/power
changes, `NaN`/positive/negative infinity, header removal/addition/rename/order
and duplication, plus same-cardinality nested-path swaps. Thus deletion,
duplication, reordering, strategy/timestamp/power alteration, non-finite values
or path/content disagreement cannot be accepted as valid publication evidence.
Focused mutation tests validate one supplied summary or one supplied nested CSV
only; the production final gate remains the separate all-882-file scan. This
keeps fault localization narrow without weakening publication coverage.
At least one non-first-row corruption is injected after final writing and must
pass through real final orchestration to diagnostic `FAIL`/nonzero CLI. The
runner-input boundary separately compares every retained core, tail, reversal
and perfect-anchor input against its immutable forecast and realized scenario
facts before publication; Schedule/Economic CRN equality alone is not enough.

A failed final contract writes a self-validating diagnostic `FAIL`
summary/findings with `OUTPUT_CONTRACT_FAILURE`; it never leaves a PENDING or
PASS publication state. The diagnostic reports its actual artifact counts rather
than claiming normal `26/882/908` topology, and a final writer exception makes
the CLI print `FAIL` and exit nonzero.

The frozen D-anchor signature includes source case/sequence/timestamps, grid
import/export, degradation, final actual SOC, terminal value, adjusted cost and
physical revisions. CRN and core/tail gates use independently constructed
expected scenario/path key sets with exact multiplicity and membership, rather
than only counts. CSV fields used for accounting are evidence representations
written at fixed 12-decimal precision; reconcile their displayed daily flows to
path totals with an absolute tolerance of `1e-9`. SVGs contain visible
short-label mapping and legends (`R`, `HP`, `HEL`, `C`, `T`, `S`, `E`), not
tooltip-only traceability. In ECDFs the visible mapping is sorted
rank-to-case-to-regret per strategy; it is not natural C01..C16 order. This
does not establish field probabilities, robust/stochastic optimization,
hardware readiness, field reliability or customer deployment readiness.
