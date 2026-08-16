# TASK-171 — Deterministic Realized Import Cost Evidence

## Goal

TASK-171 provides pure accounting evidence for one TASK-168 component: realized
import cost from caller-supplied realized grid-import energy and one explicit
import tariff.

## Contracts

- `ImportCostInput`
- `ImportCostEvidence`
- `ImportCostBoundary`
- `DeterministicImportCostCalculator`

## Frozen formula

```text
realized_import_cost =
    realized_import_energy_kwh
    * import_tariff_per_kwh
```

Both values must be finite and non-negative; zero is valid. The result retains
the exact caller-owned input identity and never caps, floors, or alters the
product.

## Separation and progression

TASK-168 aggregates four already-computed accounting components. TASK-169
provides export revenue evidence and TASK-170 provides battery degradation-cost
evidence. TASK-171 completes the fourth boundary by providing realized import
cost evidence that can be supplied directly to TASK-163 or TASK-168.

The caller owns import-energy and tariff semantics. Cross-path comparison needs
consistent import-energy and tariff bases; this boundary cannot enforce that.
It neither derives import from grid signs nor introduces TOU/dynamic tariffs,
demand/fixed charges, grid fees, tax, forecasts, planning, MPC, feasibility,
actuation, or simulation. It remains accounting evidence, not a control
objective.
