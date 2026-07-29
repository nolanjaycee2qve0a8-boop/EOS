# TASK-037 ? Self Consumption EMS Policy

## Status

IN REVIEW

## Objective

Introduce `SelfConsumptionPolicy` as the first concrete implementation of
`DecisionContextPolicyImplementation`.

The policy expresses a battery power intention from the instantaneous
photovoltaic generation and load imbalance. It creates decision intent only;
it does not execute or control devices.

## Architecture

~~~text
EnergySystemState
        |
        v
DecisionContext
        |
        v
SelfConsumptionPolicy
        |
        v
DecisionContextResult
        |
        v
DecisionIntent
~~~

## Strategy Contract

The policy uses only:

- `DecisionContext.pv_power_kw`, in kW; and
- `DecisionContext.load_power_kw`, in kW.

Its deterministic rules are:

~~~text
PV > load  -> charge by PV - load
PV < load  -> discharge by load - PV
PV = load  -> idle
~~~

`DecisionIntent.battery_power_intent_kw` retains the existing literal kW
contract:

- greater than zero means charging intent;
- less than zero means discharging intent;
- zero means idle.

Examples:

~~~text
PV 5 kW, load 2 kW -> +3 kW
PV 1 kW, load 4 kW -> -3 kW
PV 4 kW, load 4 kW ->  0 kW
~~~

## Constraint Separation

The policy intentionally does not read or enforce:

- SOC or reserve SOC;
- maximum charge or discharge power;
- battery capacity;
- export limit; or
- device capability.

Those concerns belong to the constraint and future execution layers. The
policy does not clip, saturate, normalize, or otherwise modify its calculated
semantic intent.

## Identity Preservation

The exact `DecisionIntent` created by the policy is supplied directly to
`DecisionContextResult`:

~~~python
result.intent is created_intent
~~~

There is no copy, reconstruction, or serialization.

## Non-goals

- PCS or BMS control.
- CAN, Modbus, MQTT, or device protocols.
- Commands, dispatch, runtime calls, or persistence.
- Optimization, forecasting, or TOU pricing.
- Battery degradation or SOC prediction.
- Charge/discharge power enforcement or SOC limit enforcement.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
