# ADR-083: Grid Energy Balance Simulation Model

## Status

Accepted

## Context

EOS EMS Simulator 1.0 now has concrete PV, Load, and Battery models. Grid
exchange must be calculated from their realized same-step results, especially
because Battery actual power can differ from requested actuation after power,
efficiency, and SOC protection.

An initial TASK-086 draft proposed `load - battery - pv` while also retaining
the frozen Battery convention that positive means charging. Those statements
conflict: subtracting positive charging power would reduce Grid import.

The Phase 6 Grid boundary accepts `GridSimulationInput` only, and that contract
must remain unchanged. Exact source-result provenance therefore belongs to the
immutable concrete model configuration for one evaluation.

## Decision

Adopt the corrected physical balance:

```text
grid_power_kw = load_power_kw + battery_power_kw - pv_power_kw
```

Add frozen/slotted `GridEnergyBalanceSimulationModel`, implementing
`GridSimulationModelBoundary` with exact fields:

- `pv_result`;
- `load_result`;
- `battery_result`.

All component results and the later Grid input must reference one exact step
identity. Identity comparison uses `is`; a value-equal reconstructed step is
rejected.

The result contains the exact `GridSimulationInput` and calculated actual Grid
power. The input's requested value is not treated as the balance source.

## Consequences

- Charging increases import and discharging decreases import consistently with
  frozen signs.
- Grid balance uses realized Battery power rather than requested actuation.
- Exact component-result provenance is retained without modifying Phase 6.
- The model is immutable configuration for one completed set of same-step
  component results; it stores no evolving state, cache, or history.
- A future application runner must explicitly coordinate component completion
  before Grid evaluation. TASK-086 does not change existing executor behavior.

## Rejected alternatives

### `grid = load - battery - pv`

Rejected because it makes positive charging reduce import and negative
discharging increase import.

### Calculate from Battery actuation instead of Battery result

Rejected because physical limits can make actual Battery power differ from the
requested actuation.

### Modify GridSimulationInput to add component results

Rejected because Phase 6 contracts are frozen.

### Mutate the Phase 7 executor to pass intermediate results

Rejected because TASK-086 is a concrete model task and Phase 7 must remain
unchanged.

### Add Zero Export, Grid limits, strategy, or device control

Rejected because the balance model observes physical exchange only.
