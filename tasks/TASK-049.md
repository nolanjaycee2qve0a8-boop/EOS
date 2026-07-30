# TASK-049 - Self Consumption Capability

## Status

IN REVIEW

## Objective

Introduce `SelfConsumptionCapability` as the second concrete
`EMSCapabilityBoundary` implementation.

The capability converts one immutable `DecisionContext` PV-load observation
into one semantic battery `DecisionIntent`. It does not enforce physical
limits or execute the result.

## Architecture

~~~text
DecisionContext
        |
        v
SelfConsumptionCapability
        |
        v
DecisionIntent
        |
        v
Future Resolution / Constraint
~~~

The capability may participate in future capability composition and intent
resolution, but TASK-049 does not connect or execute those boundaries.

## Public Contract

~~~python
class SelfConsumptionCapability(EMSCapabilityBoundary):
    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionIntent: ...
~~~

Public import:

~~~python
from capability import SelfConsumptionCapability
~~~

## Input Facts

The capability reads only:

- `DecisionContext.pv_power_kw`, literal unscaled photovoltaic power in kW;
  and
- `DecisionContext.load_power_kw`, literal unscaled load power in kW.

Both values are already validated as non-negative finite observations by the
immutable `DecisionContext` contract.

The capability does not read:

- SOC or reserve SOC;
- battery power limit or energy capacity;
- grid power or export limit;
- electricity price; or
- timestamp.

## Deterministic Rule

~~~text
battery_power_intent_kw = pv_power_kw - load_power_kw
~~~

Therefore:

- PV surplus produces a positive charging intent;
- PV deficit produces a negative discharging intent; and
- balanced PV and load produce zero idle intent.

Examples:

~~~text
PV 5 kW, load 2 kW -> +3 kW charging intent
PV 1 kW, load 4 kW -> -3 kW discharging intent
PV 4 kW, load 4 kW ->  0 kW idle intent
~~~

The result uses the existing `DecisionIntent.battery_power_intent_kw` contract.
No scaling, conversion, clipping, saturation, or rounding occurs.

## Constraint Separation

`SelfConsumptionCapability` expresses the complete instantaneous PV-load
imbalance as business intent.

It does not enforce:

- upper SOC or reserve SOC;
- maximum charge or discharge power;
- grid import or export limits;
- zero-export behavior; or
- PCS/BMS/device capability.

Physical feasibility remains owned by the Constraint layer.

## Statelessness

The implementation:

- uses empty slots;
- stores no fields or mutable containers;
- owns no cache or history;
- owns no Runtime, Dispatcher, Device, Constraint, or external service; and
- does not mutate `DecisionContext`.

A frozen dataclass is not applicable because the implementation has no data
fields.

## Policy Coexistence

TASK-037 already provides `SelfConsumptionPolicy` through the independent
`DecisionContextPolicyImplementation` contract.

TASK-049 does not modify, inherit, call, adapt, migrate, or replace that policy.
The two implementations express the same narrow PV-load rule through separate
accepted extension boundaries:

~~~text
SelfConsumptionPolicy     -> DecisionContextResult
SelfConsumptionCapability -> DecisionIntent
~~~

No compatibility layer is introduced.

## Existing Contract Stability

TASK-049 does not modify:

- `DecisionIntent`;
- `EMSCapabilityBoundary`;
- `CapabilityCompositionBoundary`;
- `IntentResolutionBoundary`;
- `TOUEnergyCapability`;
- Policy contracts or `SelfConsumptionPolicy`;
- Constraint contracts or implementations;
- Evaluation Integration or Cycle;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Dependency Direction

Allowed:

~~~text
SelfConsumptionCapability -> EMSCapabilityBoundary
SelfConsumptionCapability -> DecisionContext
SelfConsumptionCapability -> DecisionIntent
~~~

Forbidden:

~~~text
Kernel -> SelfConsumptionCapability
SelfConsumptionCapability -> Policy
SelfConsumptionCapability -> Constraint / Evaluation
SelfConsumptionCapability -> Runtime / Execution / Dispatch
SelfConsumptionCapability -> Device / Persistence / Telemetry
~~~

## Non-goals

- SOC or reserve SOC enforcement.
- Battery charge/discharge power limiting.
- Grid import/export limiting or zero-export logic.
- PCS, BMS, CAN, Modbus, MQTT, or device control.
- Runtime, command generation, dispatch, or execution.
- Intent composition or resolution execution.
- Optimization, MPC, forecasting, scheduling, or pricing.
- Persistence, telemetry, cache, history, retry, or rollback.

## Tests

Focused tests cover:

- concrete capability boundary inheritance and exact signature;
- PV surplus charging intent;
- PV deficit discharging intent;
- balanced idle intent;
- raw kW sign semantics;
- absence of SOC and battery power enforcement;
- independence from grid, price, and export facts;
- immutable context preservation;
- invalid context type;
- empty slots and no instance state;
- Policy independence;
- dependency isolation; and
- public import.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
