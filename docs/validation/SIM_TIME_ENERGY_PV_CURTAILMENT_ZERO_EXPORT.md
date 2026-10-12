# PV AC-port curtailment and dynamic Zero Export — simulation acceptance

Baseline: `0c63698ae9bb40b6ce994c44f296d11f187dba79` on `baseline/sim-time-energy`. This is a **separate test-only execution entry**. It does not replace `DailySimulationRunner`, change the accepted grid-charge interlock, alter frozen `ems_simulator/time_energy.py`, or connect to a device.

## AC/DC topology and what is actually controlled

The existing model is a **single AC bus**. PV and battery power are treated as AC-port contributions: load is positive consumption, battery is positive when charging and negative when discharging, and grid is positive for import and negative for export. For every physical slice,

`grid_kW = load_kW + actual_battery_kW - delivered_PV_kW`.

The new test-only executor exposes an idealized **AC PV inverter injection cap**, not a DC-array or MPPT model. External facts supply available PV (maximum 5 kW in these scenarios). Actual delivered PV is **at most** `min(available_PV, current_AC_cap)` and is also subject to a separate AC output ramp when available PV rises; a sudden irradiance loss may force an immediate output decrease. The non-delivered amount is measured as **curtailed available PV**; it is never sent into the existing physical integrator or silently destroyed. The model does not determine DC conversion, per-phase imbalance, reactive power, inverter thermal limits, true PV irradiance, or physical source provenance. Battery limits remain the existing ±3 kW and 10 kWh / 0.95-efficiency / 0.2-hard-floor model. Existing battery conversion loss is computed **once** from actual battery energy and SOC change. No invented PV conversion loss is added.

## Three independent layers and same-time order

1. The unchanged simple EMS rule reads source facts and feedback SOC at the scheduled control ticks (`0`, `3600` seconds by default) and holds its original request between ticks. An external event is **not** an extra economic decision.
2. The independent fast execution layer observes PV availability, load, grid-charge permission and Zero Export mode only at its declared check instants. It applies observations after the declared execution delay, constrains the existing battery request, and sets the PV AC-port cap. **Startup is fail-closed:** before the first observation effect, PV cap, PV delivery and battery execution request are zero; the t=0 source fact is not silently treated as an already-matured measurement. Under Zero Export it gives PV priority for serving the observed load, caps battery discharge to the observed residual load, then allows PV for battery charging only while the battery can physically accept charge. A withdrawn grid-charge permission also limits a positive request to the observed PV surplus and to the **current actually delivered PV surplus** so PV slew cannot invent permitted grid-to-battery charging. This is model-net allocation, not proof of electron provenance. Once a revoke latches a positive old request, permission restoration alone does not clear the latch; a fresh scheduled EMS decision is required.
3. Frozen `simulate_time_energy` alone computes actual battery power, SOC, grid power and import/export energy from the constrained battery request and **delivered** PV. The executor never overwrites a negative grid result after the fact. External facts, checks/effects, PV slew steps, EMS ticks and SOC limits form physical slice boundaries; record/display cadences never cause a decision.

At a shared timestamp, source facts become right-continuous; previously scheduled observation effects mature; a scheduled EMS decision reads current facts/SOC; executor targets are updated; then PV actuator movement and physical integration cover the following half-open interval. A same-time permission, mode, PV/load or reserve-target change is one external boundary, not an extra EMS call. Observation at `t` uses source facts at `max(0,t-observation_delay)`. The dynamic executor never silently checks on a source event. The ideal mode separately adds a zero-delay check exactly at such an event. A full-SOC boundary can cause immediate ideal-model retargeting; the delayed model waits for its next observation effect and records any transient.

## Predeclared hypothetical actuator settings and budgets

All values below are explicit **simulation assumptions**, not PCS/BMS/PV-inverter specifications:

| Item | Ideal limit case | Dynamic case |
| --- | ---: | ---: |
| Scheduled execution check period | 60 s, plus event checks in ideal mode | 60 s, no event-driven check |
| Observation delay | 0 s | 20 s |
| Execution delay | 0 s | 10 s |
| AC PV port rating | 5 kW | 5 kW |
| AC PV cap slew | instantaneous | 1 kW per completed simulated second |
| Battery charge/discharge limit | ±3 kW | ±3 kW |
| EMS control period | 3600 s | 3600 s |

The **ideal model** must have `export_peak ≤ 1e-9 kW`, `export_energy ≤ 2e-9 kWh` and zero export duration in every source-Zero-Export interval. This is a mathematical limit case, not physical certification. For a single dynamic disturbance, the conservative response budget is `20 + 60 + 10 + 5/1 = 95 s`. With at most 5 kW available PV and 3 kW battery discharge, a conservative peak limit is `8 kW`, and a per-contiguous-excursion energy limit is `8 × 95 / 3600 = 0.211111111 kWh`. These are **pre-run upper bounds**, not a permission to call transient export strict Zero Export. Multiple distinct disturbances can produce separate excursions; their total across two hours need not fit a one-disturbance budget. The ledger separately records every source-mode Zero Export interval's measured peak, duration, and export energy. A response not settled within its budget is a FAIL, not a hidden waiver.

Power-balance tolerance: `1e-9 kW`. Energy, storage and cross-step tolerance: `2e-9 kWh`; SOC: `1e-9`; event time: `1e-7 s`. These are numerical comparison bounds, not relaxed physical limits. Physical integration steps are independently set to 3600, 60 or 15 s, while mandatory fact/check/effect/SOC boundaries still split those steps. Keeping control/check/event times fixed, cross-step totals must agree within those bounds. Changing only record/display periods must leave decisions and physical totals **exactly identical**. Changing control period can change the strategy response and is not treated as integration error.

## Pre-run scenario expectations

| Scenario | Expected result and boundary |
| --- | --- |
| Old full-battery replay | Load 1 kW, available PV 5 kW, full battery, 7200 s. Old no-curtailment model genuinely exports 4 kW × 7200 s = **8 kWh**. Ideal curtailment must instead deliver 1 kW PV for 2 kWh, curtail 4 kW for 8 kWh, hold SOC 1, and buy/sell 0 kWh. The dynamic executor starts with no mature observation, so initially imports for load and curtails PV; this safe-start import is **not** hidden or counted as transient export. |
| Full-battery PV jump | At 1800 s PV jumps 0→5 kW and Zero Export is enabled; old discharge request remains until the next EMS tick. Ideal check coordinates PV and battery at the event. Dynamic observation and slew must expose any pre-correction export and then settle. |
| PV jump with charge room | Available PV 0→5 kW mid-hour; requested charge may absorb part of the increase. Do not require an export merely because PV rose; account delivered/curtailed energy honestly. |
| Load drop / battery-only export | Load falls between EMS ticks. PV curtailment alone cannot cure export caused by stale battery discharge; the execution layer must also cap battery discharge, with dynamic lag recorded. |
| Battery charge limit / full SOC | PV surplus above 3 kW charge acceptance is curtailed. If charging reaches SOC 1 mid-interval, frozen physics splits the slice; ideal executor retargets at the exact boundary, dynamic model records the response lag. |
| PV and battery together | Both ports can deliver into the AC bus. Zero Export requires coordinating their **sum**, not independently approving two outputs against the same load. |
| PV loss | Falling availability reduces delivered PV immediately but cannot create phantom energy. Import may rise; no PV generation is invented. |
| Mode switch | A Zero Export enable event is instantaneous only in ideal mode; dynamic mode must wait for its specified observation/effect/ramp and truthfully count intervening export. |
| Permission and reserve target | Grid-charge permission can be revoked while a soft reserve target remains high. The old EMS request is retained for comparison; source-gated actual charging must settle to PV-only without banning ordinary grid purchases for load. The accepted old interlock regression remains valid. |
| Simultaneous event | PV/load, permission, mode and reserve target change at one timestamp. Apply the declared order once, without extra EMS ticks or collapsing distinct later observations. |

For every slice the unique ledger must retain original and constrained request, actual battery power, source permission, Zero Export mode, available/delivered/curtailed PV, PV cap, load, signed grid power, separate import/export, SOC, grid-to-battery energy and battery conversion loss. Its conservation checks are `available_PV = delivered_PV + curtailed_PV`, `load + actual_battery - delivered_PV = grid`, and `load_kWh + battery_kWh - delivered_PV_kWh = import_kWh - export_kWh`. A no-curtailment comparison remains a real prior failure, not retroactively erased by a new result.

## Evidence and status

Initial targeted development run: `25 passed, 3 failed` due to sub-ULP, zero-energy SOC-boundary slices becoming duplicate absolute timestamps. The new ledger omits only unrepresentable zero-duration/zero-SOC-change rows; it does **not** discard physical energy or relax the conservation assertion. A later scenario-specific test was corrected twice: first to explicitly switch into Zero Export at the PV jump, then to assess the first disturbance window before the next hourly EMS decision rather than claim an all-day post-1875 zero-export result. Independent review identified an initial-state observation bypass; startup was changed to fail closed until the first effect. The first focused run after that change returned `29 passed, 2 failed`; those two expectations had assumed unobserved startup export and immediate PV output after a source jump, contradicting the corrected contract. Those failed runs remain part of the development record.

Final validation used `C:\Users\22908\Desktop\eos-codex\task-docs-worktree\.venv\Scripts\python.exe`, a fresh `--basetemp` per pytest group, cacheprovider disabled, and a dedicated process-only `TMPDIR/TEMP/TMP` for Campaign and full pytest. The persistent stdout/stderr, exit files and manifests are under `C:\Users\22908\Desktop\eos-codex\evidence-pv-curtailment-20261012`.

| Final gate / actual command | Terminal result | Exit |
| --- | --- | ---: |
| `python -m pytest tests/unit/ems_simulator/test_pv_curtailment_probe.py -q --basetemp <fresh> -p no:cacheprovider` | 33 passed in 1.22 s | 0 |
| `python -m pytest` on `test_time_energy.py`, `test_closed_loop_time_energy_probe.py`, `test_dynamic_constraint_probe.py`, `test_grid_charge_interlock_probe.py` and `test_pv_curtailment_probe.py` with fresh basetemp | 112 passed in 3.08 s | 0 |
| `python -m pytest` on Campaign A–F six files, with process-only dedicated temp and fresh basetemp | 62 passed in 1250.82 s (0:20:50) | 0 |
| `python -m pytest -q --basetemp <fresh> -p no:cacheprovider`, with separate process-only temp | 2919 passed in 1022.47 s (0:17:02) | 0 |
| `python -m ruff check .` | All checks passed | 0 |
| `python -m ruff format --check .` | 846 files already formatted | 0 |
| `python -m mypy --explicit-package-bases tools/pv_curtailment_probe.py tests/unit/ems_simulator/test_pv_curtailment_probe.py` | Success, no issues in 2 source files | 0 |

The independent reviewer first identified a blocking implicit t=0 observation bypass. The executor and contract were corrected to fail closed before the first delayed effect; new tests assert zero startup PV/battery execution and ordinary load import. The reviewer also requested a direct AC output-ramp assertion and genuine concurrent PV/battery load coverage. Both were added. Its final read-only verdict is **KEEP** for this simulation boundary; the reviewer did not itself run pytest. Earlier failed development runs are not overwritten by the later PASS results.

For the old full-battery case, the comparison CSV (`full-battery-comparison.csv`) records the actual model totals:

| Model | Available PV | Delivered PV | Curtailed PV | Battery energy | Grid import | Grid export | Final SOC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Old, no curtailment | 10 kWh | 10 kWh | 0 | 0 | 0 | **8 kWh** | 1.0 |
| Ideal, zero delay | 10 kWh | 2 kWh | 8 kWh | 0 | 0 | **0** | 1.0 |
| Dynamic, delayed + slew, fail-closed startup | 10 kWh | 1.996666667 kWh | 8.003333333 kWh | 0 | 0.003333333 kWh | **0** | 1.0 |

In the dynamic full-battery replay, the initial 0.003333333 kWh is explicit **load import** while the executor waits for the first observation and the PV AC output ramps; it is not an unexplained energy loss. PV energy still closes to 10 kWh. Across the separate dynamic event scenarios, transient export is honestly retained: for example load drop produced 3 kW peak / 73 s / 0.060000000 kWh, battery-only stale discharge produced 3 kW / 70 s / 0.058333333 kWh, and full-battery PV jump plus a later hourly-request/SOC event produced 5 kW peak / 116.019 s **total across more than one excursion** / 0.130849492 kWh. The 95 s / 0.211111111 kWh budget is asserted **per contiguous excursion**, not falsely against all events accumulated over two hours. The 22 per-scenario/mode CSV ledgers and SVG teaching curves are under `scenario-results/` in that evidence directory.

Local commit, persistent recovery package, checksum verification and fresh-directory restore are separate gates and are recorded only after completion. This simulation does not demonstrate hardware Zero Export, PCS/BMS response, a certified interlock, closed-loop product integration or replacement of `DailySimulationRunner`.
