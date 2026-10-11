# Legacy Demo / time-energy sidecar comparison

## Pre-run contract (fixed before comparison)

This is a test-only, fixed-request physical accounting comparison. The old
`DailySimulationRunner` runs once per scenario; the sidecar records each
`trace.simulation_input.battery_input.actuation.battery_power_kw` as the **request**
and replays that exact 24-value sequence to `simulate_time_energy`. It never
replays `battery_result.actual_power_kw` as a request and never asks the old
strategy to decide again from the new SOC.

Both paths receive the same 24 hourly PV/load values, initial SOC, capacity,
charge/discharge efficiency, power limits, and reserve SOC. The new physical
step is 3600 simulation seconds; its explicit SOC event may split a step.
The old model instead represents an SOC-limited hour by one reduced, constant
hour-average actual power. Grid power uses `load + actual battery - PV`;
positive battery power charges, positive grid power imports. Old import/export
are separated by the sign of each **hourly** grid result. New import/export
are integrated separately over each `EnergySlice`, never derived from net kWh.

The acceptance limit, chosen before execution, is absolute `1e-10` for each
hour-end SOC (unitless), duration-weighted average actual battery power (kW),
charge/discharge energy (kWh), import energy (kWh), and export energy (kWh).
This is a numerical comparison threshold for 24 one-hour evaluations, not a
physical meter tolerance. Any larger difference is reported, not excused by
changing the limit. Sub-hourly actual-power shapes are intentionally different
when an SOC boundary falls inside an hour, so they are not asserted equal.

Four 24-hour cases are fixed: unchanged Demo profile with a larger battery
(`normal_day`); first-hour upper-bound hit (`upper_bound`); first-hour lower
reserve hit (`lower_bound`); and a lower-bound event exactly at hour 1 followed
by a PV/load/request change (`hour_boundary`). They cover fixed-request
physical accounting only. They do not validate closed-loop redispatch, meter
sampling, pause/restart, protocol or hardware behavior.

## Results

Command: `python -m tools.compare_legacy_time_energy --output-dir <fresh-dir>`.
The actual executable used was Python 3.14.6 at
`C:\Users\22908\AppData\Local\Python\pythoncore-3.14-64\python.exe`.
Exit code: `0`. The full 24-hour × 4-scenario × 6-measure table is
`hourly_comparison.csv`; exact physical inputs and the **recorded old requests**
are in `replay_inputs.json`. Both files are retained at
`C:\Users\22908\.codex\visualizations\2026\08\28\01a04621-bea7-7360-bd03-f5cdc3c22942\eos-legacy-time-energy-sidecar-20261011-v2\`
and will also be included in the recovery package.

| 24-hour case | End SOC | Charge kWh | Discharge kWh | Import kWh | Export kWh | Out-of-limit rows / 144 | Largest absolute delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| normal day | 0.511105263158 | 22 | 18.8 | ~0 | 7 | 0 | 0 |
| upper bound | 1 | 0.210526315789 | 0 | 0 | 2.789473684211 | 0 | 2.78e-17 |
| lower bound | 0.2 | 0 | 0.095 | 2.905 | 0 | 0 | 4.44e-16 |
| hour boundary | 0.4 | 2 | 3 | 0 | 0 | 0 | 0 |

Representative first-hour facts show why the request must not be replaced by
the old delivered average:

| Case | Recorded request kW | Old delivered average kW | New delivered average kW | New within-hour shape |
| --- | ---: | ---: | ---: | --- |
| upper bound | +3 | +0.210526315789 | +0.210526315789 | +3 until full, then 0 |
| lower bound | -3 | -0.095 | -0.095 | -3 until reserve, then 0 |
| hour boundary, hours 0 → 1 | -3 → +2 | -3 → +2 | -3 → +2 | event exactly at 3600 s; no duplicated hour |

No material hourly or daily discrepancy appeared in these four cases. The
non-zero deltas are floating-point roundoff, far below the predeclared limit.
The old model's constant-hour approximation and the new model's boundary-event
split are **not** equal sub-hourly power histories. Also, these old strategy
requests make pre-bound grid power zero or same-sign as post-bound grid power;
the four scenarios therefore do not exercise an intra-hour import/export sign
reversal. The sidecar explicitly integrates positive and negative new grid
power separately but does not prove the old hourly export method would agree
under arbitrary external requests.

Recommendation: keep the new module in parallel for physical accounting and
retain the recorded-request comparison as a regression. Do not replace the
legacy runner or claim closed-loop scheduling equivalence. Before integration,
define the external request schedule and the interval meter/grid settlement
contract, then separately validate redispatch when SOC trajectories diverge.

Regression record:

- Focused sidecar: `python -m pytest
  tests/unit/ems_simulator/test_legacy_time_energy_sidecar.py --basetemp
  <fresh-dir> -p no:cacheprovider -q` → `7 passed in 10.50s`, exit `0`
  (Python 3.14.6).
- First full run under the sandbox's system Temp: `2677 passed, 149 errors`,
  exit `1`; the failures were file/fixture setup errors under the sandbox Temp,
  not a full-suite PASS.
- Second full run under Python 3.12 with a dedicated `--basetemp` but default
  process Temp: `2824 passed, 2 failed`, exit `1`; both failures were Campaign E
  cleanup `WinError 5` at `tempfile`'s default system Temp. These results remain
  failures, not retroactive passes.
- Targeted Campaign E retry with fresh process-only `TEMP`/`TMP`/`TMPDIR` and
  `--basetemp`: `2 passed, 3 deselected`, exit `0`.
- Final full run with fresh process-only Temp and basetemp, using Python 3.12.14:
  `python -m pytest --basetemp <fresh-dir> -p no:cacheprovider -q` →
  **`2826 passed in 872.79s`, exit `0`**. This run includes Campaign A–F;
  no test was skipped or weakened to obtain the result.

The recovery package records the exact executable, directories, commands and
outputs. No physical or device control is claimed.
