# TASK-170 — Deterministic Battery Degradation Cost Evidence

## Goal

TASK-170 provides pure accounting evidence for the battery-degradation-cost
component accepted by TASK-168. It converts caller-supplied aggregated battery
throughput and a caller-assigned unit cost into a cost scalar.

## Contracts

- `BatteryDegradationCostInput`
- `BatteryDegradationCostEvidence`
- `BatteryDegradationCostBoundary`
- `DeterministicBatteryDegradationCostCalculator`

## Frozen formula

```text
battery_degradation_cost =
    battery_throughput_kwh
    * degradation_cost_per_throughput_kwh
```

Both values must be finite and non-negative; zero is valid. The result retains
the exact caller-owned input identity and never caps, floors, or alters the
product.

## Caller-owned throughput semantics

`battery_throughput_kwh` is a caller-selected accounting basis. TASK-170 does
not decide whether it represents charge-only, discharge-only, combined, AC-side,
DC-side, or internal-cell energy. Cross-path comparisons require the caller to
use a consistent throughput definition and cost-rate semantic; this boundary
cannot enforce that coherence.

## Separation

TASK-168 accepts `battery_degradation_cost` as an already-computed scalar.
TASK-170 supplies deterministic evidence for it, which may be passed directly
to TASK-168 without conversion. It remains accounting evidence, not a control
objective: no EFC/cycle counting, SoH, replacement model, calendar/temperature
aging, DoD/C-rate model, Simulator, SOC/power trace, planning, MPC, or dispatch
behavior is introduced.
