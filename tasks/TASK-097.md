# TASK-097 — Battery Operating Envelope Feasibility Boundary

## Objective

Add an immutable Battery physical operating-envelope contract and an abstract feasibility
boundary. The TASK records whether an `EMSDecision` is inside caller-supplied limits; it
does not change that Decision or calculate a correction.

## Architecture

```text
EMSDecision + DecisionProvenance + BatteryOperatingEnvelope
    |
    v
BatteryOperatingEnvelopeBoundary
    |
    v
BatteryOperatingEnvelopeFeasibility
```

## Operating-envelope facts

`BatteryOperatingEnvelope` is frozen and slotted. It defines:

- `minimum_soc` and `maximum_soc`: finite raw unitless fractions in `[0, 1]`;
- `maximum_charge_power_kw`: finite non-negative raw kW magnitude;
- `maximum_discharge_power_kw`: finite non-negative raw kW magnitude.

The facts are supplied explicitly by the caller so the abstract boundary remains
stateless. No limits are read from a Device or retained between evaluations.

## Feasibility evidence

`BatteryOperatingEnvelopeFeasibility` preserves exact references to:

- source `EMSDecision`;
- source `DecisionProvenance`;
- source `BatteryOperatingEnvelope`.

It adds only a strict Boolean feasibility fact. It has no corrected power, replacement
Decision, actuation, Command, or execution state.

## Example semantics

- Charge may be feasible when SOC is below maximum SOC and requested magnitude does not
  exceed maximum charge power.
- Discharge may be feasible when SOC is above minimum SOC and requested magnitude does
  not exceed maximum discharge power.
- Boundary SOC or excess power may be represented as infeasible.

The production TASK defines no concrete algorithm. Focused tests use a test-only
implementation to demonstrate these semantics.

## Non-goals

- no power clipping or corrected Decision;
- no Strategy generation or modification;
- no Battery state transition or SOC calculation;
- no PCS, Device, Command, Dispatcher, Runtime, or execution;
- no Grid control, Zero Export algorithm, Simulator call, or Optimization;
- no modification to TASK-090–096 or Phase 5–8 contracts.

## Validation

- frozen/slotted envelope and result contracts;
- exact Decision, Provenance, and Envelope identities;
- reconstructed artifact rejection;
- charge/discharge feasibility examples;
- SOC-boundary and power-limit infeasibility examples;
- abstract/stateless boundary, dependency isolation, full pytest, Ruff, mypy, and diff
  validation.
