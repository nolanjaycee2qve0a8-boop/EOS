# TASK-139 - Longer-Horizon Headroom-Aware 24h MPC Demo

## Objective

Add a runnable deterministic 24-hour comparison demo using the existing
TASK-138 `HeadroomAwareExplainableMPCDailySimulationRunner`. The demo supplies
24 caller-owned forecast horizons with 24 points each so every hourly cycle can
observe a full repeating-day future PV/load/tariff window.

## Implementation

- Add `ems_simulator.headroom_aware_mpc_demo` with the CLI:

  ```text
  python -m ems_simulator.headroom_aware_mpc_demo \
      --output-dir simulation_output_headroom_mpc
  ```

- Reuse the frozen TASK-129 scenario: the same daily PV, load, tariff, start
  timestamp, 10 kWh battery, 0.50 initial SOC, 0.20 reserve/min SOC, 3 kW
  charge/discharge limits, efficiencies, and one-hour step duration.
- Compose existing TASK-132 through TASK-138 components only:
  PV headroom requirement, cheap-grid reservation, headroom candidate planner,
  explicit physical revision, headroom physical optimization, headroom MPC
  cycle, existing explanation/CSV seams, feasibility/handoff, and simulator.
- Use the distinct `headroom-aware-net-load-mpc` strategy and capability
  identity.
- Write the standard five files without changing prior demo output schemas:
  `mpc_decisions.csv`, `simulation_result.csv`, `power_curve.svg`,
  `soc_curve.svg`, and `daily_summary.txt`.

## Forecast convention

The 24-point horizon is explicit demo data. Points use the daily profiles with
modulo-24 wrapping after midnight. This is deterministic comparison input only,
not a forecast provider, runtime scheduler, or production weather model.

## Behavioral evidence

Every daily trace retains its exact outer `HeadroomAwareMPCCycleResult`, so the
original net-load candidate, PV headroom requirement, optional grid-charge
reservation, reservation-adjusted candidate, physical revision, and final
decision can be inspected without changing the existing physical explanation
or decision CSV schema.

The summary adds deterministic headroom metrics:

- grid-charge reservation count;
- reduced and zeroed reservation counts;
- minimum recommended pre-PV maximum SOC;
- maximum required headroom energy.

## Measured deterministic comparison

The three CLIs were run against the identical TASK-129 scenario. The
historical price-only baseline exported 33.800000 kWh, the historical
net-load-aware baseline exported 29.000000 kWh, and this longer-horizon
headroom-aware demo exported 23.736842 kWh. Its Grid import was 11.200000 kWh
and final actual SOC was 0.200000.

The headroom-aware run produced six cheap-grid-charge reservations; all six
reduced the 3 kW candidate to zero because actual SOC started above the
0.200000 recommended pre-PV maximum. PV-surplus steps retained no reservation
and still charged the battery where physical limits allowed. This is measured
demo behavior, not an export target or an optimizer formula change.

## Boundaries preserved

TASK-129 price-only and TASK-131 net-load-aware demos remain unchanged.
No optimization formulas, new architecture contracts, explanation schema,
physical constraint, horizon scheduling, runtime, device behavior, or forecast
generation are added. The new demo remains a finite 24-step invocation of the
existing TASK-138 runner.
