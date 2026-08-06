# EOS Phase 6 Simulation Architecture v1.0

## 1. Phase objective

Phase 6 establishes the immutable contracts required to simulate one explicit
energy-system observation without turning Simulation into Runtime or Device
Execution.

The phase answers four questions:

1. How is one simulation step identified without owning a clock?
2. How do component models receive and return explicit immutable facts?
3. How is a feasible Battery decision traced into simulation actuation?
4. How are component observations aggregated without re-execution or hidden
   progression?

## 2. Completed tasks

| TASK | Contract | Result |
| --- | --- | --- |
| TASK-065 | Simulation core identity/time | Explicit sequence, duration, optional aware timestamp |
| TASK-066 | PV model contract | Immutable availability input and generation result |
| TASK-067 | Load model contract | Immutable demand input and consumption result |
| TASK-068 | Tariff model contract | Immutable timestamped import/export price facts |
| TASK-069 | Battery actuation contract | Exact feasible-decision provenance and signed power |
| TASK-070 | Battery model contract | Immutable source/next state transition seam |
| TASK-071 | Grid model contract | Immutable requested/actual Grid exchange facts |
| TASK-072 | Aggregate contracts | Step input, state, result, and scenario evidence |
| TASK-073 | Integration validation | Exactly-once test models and end-to-end identity checks |
| TASK-074 | Completion review | Phase 6 architecture freeze |

## 3. Frozen architecture

```text
SimulationStepIdentity
        |
        +--> PV Input      -> PV Boundary      -> PV Result
        +--> Load Input    -> Load Boundary    -> Load Result
        +--> Tariff Input  -> Tariff Boundary  -> Tariff Result
        +--> Battery Input -> Battery Boundary -> Battery Result
        +--> Grid Input    -> Grid Boundary    -> Grid Result
        |
        v
SimulationStepInput
        +
exact component results
        |
        v
SimulationState
        |
        v
SimulationStepResult

caller-ordered tuple[SimulationStepInput, ...]
        |
        v
SimulationScenario
```

Battery decision provenance:

```text
FeasibleDecisionIntent
        |
        v
BatterySimulationActuation
        |
        v
BatterySimulationInput
        |
        v
BatterySimulationResult
```

## 4. Core contracts

### Identity and time

`SimulationStepIdentity` carries caller-supplied sequence, duration, and
optional aware timestamp. It reads no clock, generates no timestamp or UUID,
and advances nothing.

### Component contracts

Each component owns its own immutable input, immutable result, and abstract
stateless model boundary. Component contracts do not call each other and do
not calculate a system-wide balance.

### Aggregate contracts

Aggregate artifacts preserve exact inputs and results. They validate direct
identity relationships but do not execute models. `SimulationScenario`
preserves an exact caller tuple and its order; it does not sort, execute, or
progress the steps.

## 5. Units and sign conventions

- Time duration: positive finite raw seconds.
- PV and Load power: non-negative finite raw kW.
- Tariff: signed finite raw CNY/kWh with an explicit aware timestamp.
- Battery SOC: raw unitless fraction in `[0, 1]`.
- Battery power: positive charging, negative discharging, zero idle.
- Grid power: positive import, negative export, zero balanced exchange.

No hidden unit scaling or implicit conversion is permitted.

## 6. Identity and provenance

Phase 6 identity guarantees are direct and explicit:

- component inputs preserve the exact step;
- component results preserve the exact component input;
- aggregate state preserves exact results;
- step result preserves exact aggregate input and state;
- scenario preserves exact caller tuple, elements, and order; and
- Battery actuation preserves the exact feasible decision.

Value-equal reconstructed objects are not provenance substitutes.

## 7. Execution evidence

TASK-073 uses concrete recording models only inside integration tests. Each
component model is invoked exactly once. Construction of aggregate state,
step result, and scenario performs no model execution.

This proves that the contracts compose correctly. It does not introduce a
production orchestrator or runner.

## 8. Layer separation

### Simulation is not Runtime

Simulation contracts describe inputs, model responses, and immutable state
observations. They do not own a loop, scheduler, current-step pointer, retry,
failure coordinator, cache, or history.

### Simulation is not Device Execution

Simulation never communicates with PCS, BMS, CAN, Modbus, MQTT, or any device.
`BatterySimulationActuation` is a model input artifact, not a Command.

### Simulation follows Decision and Constraint

The Battery provenance chain consumes an already completed
`FeasibleDecisionIntent`. Simulation does not recalculate policy or constraints
and does not modify Phase 5 contracts.

## 9. Phase 6 non-goals

- No production PV, Load, Tariff, Battery, or Grid model.
- No power-balance, SOC-transition, physics, loss, efficiency, degradation,
  forecasting, or optimization algorithm.
- No runner, automatic step progression, Runtime, Scheduler, or clock owner.
- No Device, Command, Dispatch, PCS/BMS, or protocol integration.
- No persistence, telemetry, database, cache, or history.

## 10. Completion conclusion

Phase 6 is PASS and frozen at TASK-074. EOS now has a stable, immutable,
identity-preserving simulation contract platform and integration evidence. It
does not yet have production physics models or a simulation execution runtime;
those capabilities require separate future architecture decisions.

