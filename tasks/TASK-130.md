# TASK-130 - Net-Load-Aware Baseline Optimizer

## Objective

Add a deterministic candidate optimizer that combines forecast price, PV power,
and load power. It improves first-order household behavior without changing the
frozen price-only baseline or the physically-aware revision layer.

## Responsibility progression

```text
PriceAwareBaselineOptimizer
    price only
        -> NetLoadAwareBaselineOptimizer
           price + PV + Load
               -> PhysicallyAwareBaselineOptimizer
                  battery SOC + battery power limits
```

These remain separate responsibilities. TASK-130 produces semantic candidate
requests only; it does not inspect battery state, capacity, efficiency, or
power limits.

## Candidate precedence

1. Forecast PV surplus charges by the exact surplus, independent of price.
2. At high price, a positive forecast load deficit discharges by that exact
   deficit only.
3. At low price with no PV surplus, the candidate requests the caller-supplied
   `requested_grid_charge_power_kw`.
4. Otherwise, the candidate is idle.

This prevents a high-price battery discharge from intentionally increasing grid
export when PV already covers load. A later physical revision may reduce a
candidate charge or discharge request while retaining exact evidence.

## Provenance and determinism

The optimizer creates one ordered solution step per exact caller forecast point,
preserving each timestamp reference. It reads no clock, performs no sorting,
does not mutate forecasts, and uses no simulator or device dependency.

## Known limitation

TASK-130 does not reserve future battery headroom for expected daytime PV. It
can still charge heavily from cheap overnight grid energy and leave insufficient
capacity before sunrise. That requires a future horizon economic/headroom task.

## Non-goals

No MILP/QP, global economic scheduling, export tariff, zero export, explicit
grid limit, PV curtailment, SOC propagation, battery clipping, Actuation, or
Simulator integration is added. TASK-129 remains on its frozen price-only demo
path; this task proves direct composition only.
