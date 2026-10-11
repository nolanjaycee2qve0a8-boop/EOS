# Closed-loop time/energy probe — pre-run contract

Baseline: local commit `ad63b72bdf60e028e57a8af16ffb6b8c75a12ab6`.
This is a separate test entry. It does not modify or invoke
`DailySimulationRunner` for closed-loop execution. At each scheduled control
instant, the sidecar reads the **new physical module's returned SOC** and
computes the next request with the legacy Demo's simple imbalance/reserve
policy. Between control instants, the request is held. External PV/load event
times split physical input intervals but **do not** trigger an extra decision.
Physical step size, record period and display period are not control clocks.

## Fixed experiment design

- One simulated day is `[0, 86400)` seconds. The primary control period is
  exactly 3600 simulated seconds: decisions at 0, 3600, ..., 82800 seconds
  (24 calls, no call at the terminal boundary). Independent comparisons use
  physical steps 3600, 60 and 15 seconds with that same event/control schedule.
- Four cases: the normal 24-hour Demo PV/load profile; upper-SOC saturation;
  lower-reserve saturation; and a within-hour PV/load event that reverses grid
  flow from import to export. A separate 1800-second control-period run is a
  **strategy change**, not an integration-equivalence assertion.
- Every case uses capacity 10 kWh, charge/discharge power limits 3 kW,
  charge/discharge efficiencies 0.95, and lower reserve SOC 0.2. Initial SOCs
  are 0.5 (normal), 0.98 (upper), 0.21 (lower), and 0.2 (reversal). Normal-day
  PV/load are the exact 24-element curves in `ems_simulator/demo.py`. Upper
  uses PV 5/load 1 kW for `[0,7200)`, then both 0; lower uses PV 0/load 3 kW
  for `[0,7200)`, then both 0. Reversal uses load 2/PV 0 kW for `[0,1800)`,
  load 1/PV 3 kW for `[1800,7200)`, then both 0. The probe source stores these
  as explicit immutable external segments.
- The external event is right-continuous: the new load/PV applies at its exact
  declared timestamp. No energy slice may straddle an external event or a
  scheduled control boundary. Each slice is integrated using its own duration.
- Positive battery power means charging. Positive grid power means import.
  For every slice: `grid = load + actual battery - PV`. Import and export are
  accumulated as separate positive integrals, not netted before accumulation.

## Acceptance limits (declared before execution)

- Simulation-time boundary: absolute `1e-9` second; scheduled control times
  and counts must be **exact integer-second identities**, with no extra call.
- Delivered power and grid-balance identity: absolute `1e-10` kW.
- SOC and cross-step SOC comparison: absolute `1e-9` (unitless).
- Energy accounting and cross-step totals: absolute
  `4e-11 kWh × simulated duration in hours`. Thus a full 24-hour comparison
  allows `9.6e-10` kWh; an individual one-hour bucket allows `4e-11` kWh.
  Slice-level storage-energy checks use the same duration scaling with a
  one-second numerical floor. These limits only allow floating-point
  summation effects; they are not real meter accuracy or product tolerances.
- SOC must stay in `[reserve_soc, 1]`; actual charge/discharge power must stay
  inside its configured kW limit, subject only to the above power tolerance.

Changing record/display periods alone must preserve decisions, SOC and energy.
Changing control period may change requests and economic/physical outcomes;
each run must still satisfy its own conservation and boundary invariants.
No assertion requires the new closed loop to match the legacy hourly runner.

## Results

The independent command
`python -m tools.closed_loop_time_energy_probe --output-dir <fresh-dir>`
finished with exit `0`. Its evidence is retained at
`C:\Users\22908\.codex\visualizations\2026\08\28\01a04621-bea7-7360-bd03-f5cdc3c22942\eos-closed-loop-probe-20261011\`:

- `summary.csv`: each scenario/step/control-period total and decision count;
- `hourly.csv`: 24 hour-end SOC, mean delivered power and separate energy
  integrals for each run;
- `decisions.csv`: exact decision time, feedback SOC and request;
- `event_window.csv`: before/after-event physical slices and grid direction.

| Case, hourly control | Physical steps tested | Decisions | Final SOC | Import kWh | Export kWh | Cross-step verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Normal Demo day | 3600 / 60 / 15 s | 24 each | 0.2 | 8.35 | 20.578947368421 | within fixed limits |
| Upper SOC limit | 3600 / 60 / 15 s | 24 each | 1.0 | 0 | 7.789473684211 | within fixed limits |
| Lower SOC reserve | 3600 / 60 / 15 s | 24 each | 0.2 | 5.905 | 0 | within fixed limits |
| Intra-hour flow reversal | 3600 / 60 / 15 s | 24 each | 0.39 | 1.0 | 1.0 | within fixed limits |

Across the six summary quantities (SOC, load/PV energy, signed battery energy,
import, export), the largest absolute 60/15-vs-3600 difference was
`1.7942e-13` for the normal day, `1.5988e-14` for upper saturation,
`1.7764e-14` for lower saturation and `5.3291e-15` for reversal. The tests
also check every hourly SOC, average delivered power and separate energy
bucket against the predeclared limits, rather than relying only on day totals.

The reversal case changes load/PV at simulated 1800 s, **without** a new
hourly-control decision. Its first half-hour imports 1 kWh and its second
half-hour exports 1 kWh. Net grid energy is 0, but the two positive ledger
entries are retained separately. No slice straddles the event. Upper/lower
cases reach their SOC bounds without exceeding configured power limits.

For context, the unchanged legacy Demo on its **same normal-day parameters**
reported final SOC 0.2, battery throughput 18.871053 kWh, import 8.35 kWh and
export 20.578947 kWh. The new hourly-control normal run reports final SOC 0.2,
charge 8.421052631579 kWh plus discharge 10.45 kWh (throughput
18.871052631579 kWh), import 8.35 kWh and export 20.578947368421 kWh.
Agreement is expected for this hourly profile and common simple policy; it
does **not** assert equivalence for a different control period, new SOC path,
or within-hour events, which the legacy 24-hour input cannot express.

With the **physical step held at 60 s**, changing only record/display periods
from `1 / 0.1 s` to `3600 / 3600 s` leaves the 24 decisions, every hourly row,
SOC and both grid-energy totals exactly unchanged. Changing **control** from
3600 to 1800 s instead creates 48 decisions. At 1800 s the controller sees
the new surplus and requests +2 kW: the reversal case then ends at SOC 0.485,
imports 1 kWh and exports 0 kWh. This difference follows a different
request schedule; both runs pass their own conservation checks. It must not
be described as an integration discrepancy.

Actual validation (Python 3.12.14, pytest 8.4.2):

- Focused: `python -m pytest
  tests/unit/ems_simulator/test_closed_loop_time_energy_probe.py --basetemp
  <fresh-dir> -p no:cacheprovider -q` → `8 passed in 1.24s`, exit `0`.
- Related new/old time-energy and legacy-runner tests, same pytest options:
  `41 passed in 2.04s`, exit `0`.
- Full project, with fresh process-only `TEMP/TMP/TMPDIR` and a distinct
  `--basetemp`: `python -m pytest --basetemp <fresh-dir>
  -p no:cacheprovider -q` → **`2834 passed in 790.92s`**, exit `0`.
  Campaign A–F is included; it was not separately claimed as a new run.
- `ruff check .`: PASS; `ruff format --check .`:
  `837 files already formatted`; scoped mypy:
  `Success: no issues found in 2 source files`; each exit `0`.

Recovery-package location and independent restore test are recorded with the
final package. This experiment is simulation-only and does not validate
device control, field metering, pause/resume or product dispatch.
