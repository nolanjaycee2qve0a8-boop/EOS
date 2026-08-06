# TASK-072 — Aggregate Simulation Contract

Status: IN REVIEW

## Objective

Define immutable aggregate contracts that compose the independently reviewed
Phase 6 PV, Load, Tariff, Battery, and Grid artifacts into consistent one-step
simulation evidence and caller-ordered scenarios.

TASK-072 aggregates existing objects only. It does not execute component
models, calculate power balance, advance steps, own Runtime, or control a
Device.

## Architecture

```text
Exact component inputs for one SimulationStepIdentity
        |
        v
SimulationStepInput

Exact component results for the same SimulationStepIdentity
        |
        v
SimulationState

SimulationStepInput + SimulationState
        |
        v
SimulationStepResult

caller-ordered tuple[SimulationStepInput, ...]
        |
        v
SimulationScenario
```

## SimulationStepInput

Frozen and slotted with exactly:

- `step_identity: SimulationStepIdentity`;
- `pv_input: PVSimulationInput`;
- `load_input: LoadSimulationInput`;
- `tariff_input: TariffSimulationInput`;
- `battery_input: BatterySimulationInput`;
- `grid_input: GridSimulationInput`.

Every component input must reference the exact aggregate step object using
identity, not value equality. All caller object references are preserved.

## SimulationState

Frozen and slotted with exactly:

- `step_identity: SimulationStepIdentity`;
- `pv_result: PVSimulationResult`;
- `load_result: LoadSimulationResult`;
- `tariff_result: TariffSimulationResult`;
- `battery_result: BatterySimulationResult`;
- `grid_result: GridSimulationResult`.

Every component result must be associated with the exact aggregate step. The
state stores the exact result objects and does not copy, normalize, or
reconstruct them.

## SimulationStepResult

Frozen and slotted with exactly:

- `simulation_input: SimulationStepInput`;
- `state: SimulationState`.

The exact step identity must be shared. Each result in `state` must reference
the corresponding exact component input in `simulation_input`:

```text
state.pv_result.simulation_input is input.pv_input
state.load_result.simulation_input is input.load_input
state.tariff_result.simulation_input is input.tariff_input
state.battery_result.simulation_input is input.battery_input
state.grid_result.simulation_input is input.grid_input
```

Equal-but-distinct reconstructed inputs are rejected because value equality is
not provenance.

## SimulationScenario

Frozen and slotted with exactly:

- `steps: tuple[SimulationStepInput, ...]`.

The tuple and every step reference preserve exact caller identity. Empty
scenarios are valid. Caller order is preserved; the contract does not sort,
deduplicate, validate chronology, execute, or advance steps.

## Dependency direction

```text
simulator.aggregate
    -> simulator component contracts
    -> simulator.core
```

No component contract depends on the aggregate package. There is no dependency
on Runtime, Device, Command, Dispatch, Capability, Policy, or Optimization.

## Non-goals

- Component model execution or orchestration.
- Power balance, energy integration, state calculation, or automatic Grid
  derivation.
- Scenario runner, loop, clock, scheduler, retry, or step progression.
- Sorting, deduplication, timeline normalization, interpolation, or forecasting.
- Runtime, Device, Command, Dispatch, PCS/BMS, CAN, Modbus, or MQTT.
- Persistence, telemetry, database, cache, history, UUID, or logging framework.

## Validation

Focused tests cover exact cross-component step identity, exact result-to-input
lineage, reconstructed-object rejection, caller ordering, tuple-only scenario
storage, empty scenarios, frozen/slotted field completeness, forbidden
execution ownership, dependency direction, public imports, and regression.
