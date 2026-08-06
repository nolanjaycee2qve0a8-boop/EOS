# TASK-068 — Tariff Simulation Model Contract

Status: IN REVIEW

## Objective

Define the immutable and abstract Phase 6 tariff simulation boundary.

TASK-068 represents explicit one-step tariff facts and one simulated tariff
observation. It introduces no TOU strategy, tariff schedule selection, price
prediction, external pricing service, Runtime, Device, Command, or concrete
model.

## Architecture

```text
SimulationStepIdentity(with aware timestamp)
        +
caller-supplied import/export price facts
        |
        v
TariffSimulationInput
        |
        v
TariffSimulationModelBoundary
        |
        v
TariffSimulationResult
```

## Input contract

`TariffSimulationInput` is frozen and slotted with exactly:

- `step_identity: SimulationStepIdentity`;
- `import_price_cny_per_kwh: float`;
- `export_price_cny_per_kwh: float`.

The step must contain an explicit timezone-aware timestamp. Prices are signed
finite raw values in CNY per kWh. Signed values are intentional because energy
markets can represent negative prices. There is no hidden scaling or currency
conversion.

The input does not read a clock, convert timezone, query an API, choose a TOU
window, or predict a price.

```text
simulation_input.step_identity is original_step_identity
```

## Result contract

`TariffSimulationResult` is frozen and slotted with exactly:

- `simulation_input: TariffSimulationInput`;
- `import_price_cny_per_kwh: float`;
- `export_price_cny_per_kwh: float`.

Result prices follow the same signed finite raw CNY/kWh contract. The Result
does not explain, predict, select, scale, or calculate either value.

```text
result.simulation_input is original_simulation_input
```

## Model boundary

`TariffSimulationModelBoundary` is abstract, stateless, and empty-slotted:

```python
def simulate(
    self,
    simulation_input: TariffSimulationInput,
) -> TariffSimulationResult: ...
```

No concrete production tariff model is introduced.

## Dependency direction

```text
simulator.tariff
    -> simulator.core
    -> simulator.validation
    -> Python standard library
```

There is no dependency on Capability, Policy, Decision Formation, Runtime,
Device, Command, external API, optimization, or forecasting.

## Non-goals

- TOU strategy, price-window selection, arbitrage, or billing.
- Tariff forecasting, schedule generation, cloud/API lookup, or currency
  conversion.
- Runtime, clock ownership, scheduler, Device, Command, or Dispatch.
- Aggregate Simulation State, Scenario, Step Result, or composition.
- Optimization, persistence, telemetry, cache, or history.

## Validation

Focused tests cover explicit aware time, signed finite raw prices, bool and
non-finite rejection, exact identity, frozen/slotted field completeness,
abstract boundary behavior, no concrete model or forbidden dependency, public
imports, and the full regression suite.
