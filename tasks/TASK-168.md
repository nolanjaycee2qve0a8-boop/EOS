# TASK-168 — Extended Economic Outcome Evidence

## Goal

TASK-168 adds a parallel, solver-independent accounting boundary for a broader
set of caller-supplied realized economic terms. It preserves TASK-163 unchanged.

## Contracts

- `ExtendedEconomicOutcomeInput`
- `ExtendedEconomicOutcomeEvidence`
- `ExtendedEconomicOutcomeBoundary`
- `DeterministicExtendedEconomicOutcomeCalculator`

## Frozen accounting semantics

```text
adjusted_net_economic_cost =
    realized_import_cost
    - realized_export_revenue
    + battery_degradation_cost
    - terminal_energy_value
```

All three supplied scalar components must be finite and non-negative; zero is
valid. The exact caller-owned `TerminalEnergyValueEvidence` is retained by
identity. The adjusted outcome may be negative and is never clamped. A negative
outcome is limited accounting evidence, not realized cash profit.

## Separation

This boundary aggregates only supplied values. It does not read or recompute
grid traces, tariffs, forecasts, battery throughput, terminal valuation,
candidate plans, decisions, MPC, feasibility, actuation, or simulation.

`EconomicOutcomeEvidence` from TASK-163 remains the narrower parallel result:

```text
net_economic_cost = realized_import_cost - terminal_energy_value
```

When export revenue and degradation cost are both zero and all shared evidence
is exact, TASK-168 produces the same numerical result as TASK-163 without
calling TASK-163 internally.
