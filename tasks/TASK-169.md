# TASK-169 — Deterministic Export Revenue Evidence

## Goal

TASK-169 introduces a pure accounting-evidence boundary for one missing
TASK-168 component: realized export revenue from caller-supplied realized export
energy and one explicit export tariff.

## Contracts

- `ExportRevenueInput`
- `ExportRevenueEvidence`
- `ExportRevenueBoundary`
- `DeterministicExportRevenueCalculator`

## Frozen formula

```text
realized_export_revenue =
    realized_export_energy_kwh
    * export_tariff_per_kwh
```

Both inputs must be finite and non-negative; zero is valid. The result retains
the exact caller-owned input identity and never applies a cap, floor, grid-sign
interpretation, or dynamic tariff model.

## Progression and separation

TASK-168 accepts `realized_export_revenue` as an already-computed scalar.
TASK-169 provides deterministic evidence for `realized export energy × export
tariff`, which can be supplied directly to TASK-168 without conversion.

Export settlement remains observational/accounting only. This task does not
derive export from grid power, alter Zero Export semantics, calculate import
economics, select time-varying feed-in tariffs, or modify planning, MPC,
feasibility, actuation, or simulation.
