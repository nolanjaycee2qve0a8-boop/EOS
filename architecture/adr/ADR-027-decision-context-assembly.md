# ADR-027 — DecisionContext Assembly Boundary

## Status

Accepted

## Context

`EnergySystemState` records physical observations, while `DecisionContext`
also requires external facts and decision constraints. Timestamp, load,
battery capacity, electricity price, reserve SOC, export limit, and the
decision-facing battery power limit are intentionally absent from the physical
state model.

Deriving these missing facts would introduce hidden calculations or policy
interpretation. Extending `EnergySystemState` would mix physical observation
with external decision inputs.

## Decision

Introduce stateless `DecisionContextAssembler` in `kernel.decision`.

The assembler maps exactly three established observations:

~~~text
state.battery.soc        -> context.soc
state.pv.actual_power_kw -> context.pv_power_kw
state.grid.grid_power_kw -> context.grid_power_kw
~~~

All remaining `DecisionContext` facts are required keyword-only arguments with
no defaults. The caller therefore owns their provenance and meaning.

The assembler validates the state boundary and required component
availability, then constructs `DecisionContext`. Existing context validation
remains the single owner of timestamp, range, finiteness, price-unit, and
constraint validation.

## Architecture

~~~text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContext
        |
        v
Future EMS Policy
~~~

## Consequences

- Physical observation remains separate from external decision facts.
- Assembly is deterministic and contains no hidden calculation.
- State-derived values preserve their existing units and sign conventions.
- The caller-supplied timestamp retains its identity and decision-instant
  meaning.
- Future policies receive the existing immutable `DecisionContext` contract.

## Rejected Alternatives

- Extend `EnergySystemState`: rejected because external facts and constraints
  are not physical observations.
- Infer one battery power limit from charge/discharge availability: rejected
  because the selection requires interpretation.
- Derive load or normalize grid power: rejected because assembly must not
  perform hidden power calculations.
- Add defaults: rejected because every decision fact requires explicit
  provenance.
- Execute policy during assembly: rejected because assembly is an input
  boundary only.
