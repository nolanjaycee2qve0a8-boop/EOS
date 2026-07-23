# ADR-007 — Immutable Power Flow Observation

## Status

Accepted

## Context

EOS requires explicit power relationships before implementing EMS policies.
PV generation, load consumption, battery exchange, and grid exchange need one
clear sign convention and one deterministic balance invariant. Placing control
or automatic correction in this model would blur the boundary between observed
domain facts and future decision behavior.

## Decision

Represent one power-balance observation as an immutable PowerFlow value with
explicit PV, load, battery, and grid power fields.

PV and load values are non-negative. Negative battery power represents
charging and positive battery power represents discharging. Positive grid
power represents import and negative grid power represents export.

Enforce:

`pv_power_kw + grid_power_kw + battery_power_kw = load_power_kw`

All values must be finite, non-boolean numbers. Balance validation uses a fixed
absolute tolerance of `1e-9 kW` with zero relative tolerance. The model validates
caller observations but does not infer, calculate, or correct them.

## Consequences

- Power-flow validation is explicit and deterministic.
- The sign convention is shared independently of any policy.
- Callers must provide a complete, balanced observation.
- Future decision policies can consume the model without owning its invariants.
- Acquisition, aggregation, and reconciliation remain external concerns.

## Alternatives Considered

- Embedding control logic: rejected because PowerFlow describes an observation,
  not a desired action.
- Automatic balance correction: rejected because it would hide invalid or
  incomplete caller data.
- Deriving a missing field: rejected because hidden power calculations weaken
  the explicit observation boundary.
- Relative tolerance: rejected because acceptance would change with the
  magnitude of the observation.
