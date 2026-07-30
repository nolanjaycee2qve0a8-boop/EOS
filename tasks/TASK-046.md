# TASK-046 - TOU Energy Capability

## Status

IN REVIEW

## Objective

Implement the first concrete Phase 3 EMS capability.

`TOUEnergyCapability` uses explicit caller-supplied time-of-use facts and the
time and electricity price already present in one immutable
`DecisionContext`. It returns one semantic `DecisionIntent`.

The capability expresses business intent only. It does not decide physical
feasibility or execute the resulting intent.

## Architecture

~~~text
DecisionContext
        |
        v
TOUEnergyCapability
        |
        v
DecisionIntent
        |
        v
existing Constraint and Evaluation boundaries
~~~

## Public Types

~~~python
@dataclass(frozen=True, slots=True)
class TOUCapabilityParameters:
    charge_hours: tuple[int, ...]
    discharge_hours: tuple[int, ...]
    charge_price_ceiling_cny_per_kwh: float
    discharge_price_floor_cny_per_kwh: float
    charge_power_intent_kw: float
    discharge_power_intent_kw: float


@dataclass(frozen=True, slots=True)
class TOUEnergyCapability(EMSCapabilityBoundary):
    parameters: TOUCapabilityParameters

    def evaluate(
        self,
        context: DecisionContext,
    ) -> DecisionIntent: ...
~~~

Public imports:

~~~python
from capability import TOUCapabilityParameters, TOUEnergyCapability
~~~

## Time Contract

`charge_hours` and `discharge_hours`:

- are tuples of integer local clock hours;
- use literal hour values from 0 through 23;
- are interpreted in the timezone already carried by
  `DecisionContext.timestamp`;
- are not sorted, converted, or normalized;
- must not contain duplicate values; and
- must not overlap.

The capability reads `context.timestamp.hour`. It performs no timezone lookup,
timezone conversion, daylight-saving policy, clock ownership, or scheduling.

## Price Contract

`charge_price_ceiling_cny_per_kwh` and
`discharge_price_floor_cny_per_kwh`:

- are literal, unscaled CNY per kWh values;
- must be finite numeric values;
- may be signed; and
- are caller-supplied tariff facts.

The capability reads the exact validated
`context.electricity_price_cny_per_kwh`. It performs no price forecast,
tariff lookup, currency conversion, or hidden scaling.

The two thresholds have no required relative ordering because charge and
discharge hour tuples are disjoint.

## Intent Power Contract

`charge_power_intent_kw` and `discharge_power_intent_kw`:

- are literal, unscaled kW magnitudes;
- must be finite and non-negative;
- express business intent, not physical equipment limits.

The existing `DecisionIntent` sign convention remains:

- positive means battery charging intent;
- negative means battery discharging intent;
- zero means idle.

## Evaluation Rules

One call applies these rules in deterministic order:

1. If the context local hour is in `charge_hours` and the context price is less
   than or equal to `charge_price_ceiling_cny_per_kwh`, return positive
   `charge_power_intent_kw`.
2. Otherwise, if the context local hour is in `discharge_hours` and the context
   price is greater than or equal to
   `discharge_price_floor_cny_per_kwh`, return negative
   `discharge_power_intent_kw`.
3. Otherwise, return zero intent.

Inclusive threshold comparisons are explicit. There is no hidden fallback,
default tariff, or automatic schedule generation.

## Immutability and Ownership

- Parameters and capability are frozen and slotted.
- The capability preserves the exact parameter object supplied by its caller.
- `evaluate()` does not mutate or retain the context.
- Every evaluation returns a new immutable `DecisionIntent`.
- No cache, history, runtime state, clock, or scheduler is introduced.

## Constraint Separation

TOU capability does not inspect or enforce:

- SOC or reserve SOC;
- battery charge or discharge capability;
- battery energy capacity;
- grid import or export limits;
- PCS/BMS state; or
- device availability.

Those facts remain available to their existing boundaries. Any generated TOU
intent must pass through the existing Constraint layer before future execution.

## Existing Contract Stability

TASK-046 does not modify:

- `EMSCapabilityBoundary`;
- `DecisionContext`;
- `DecisionIntent`;
- `DecisionContextPolicy` or `DecisionContextResult`;
- `DecisionConstraintBoundary`;
- `ConstraintEvaluationPipeline`;
- `DecisionEvaluationIntegration`;
- `DecisionEvaluationCycle`;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Non-goals

- TOU optimization or tariff discovery.
- Forecasting, MPC, or optimization solver integration.
- Peak shaving, self-consumption, zero export, or pricing recommendation.
- SOC, battery power, or grid feasibility enforcement.
- Command generation, dispatch, runtime, PCS/BMS, or device control.
- Persistence, telemetry, cache, history, scheduling, or retries.

## Tests

Focused tests cover:

- boundary implementation and signature;
- low-price charging;
- high-price discharging;
- inclusive thresholds;
- idle behavior outside matching time/price conditions;
- explicit hour validation and non-overlap;
- finite price and non-negative power contracts;
- frozen/slotted parameter and capability models;
- exact parameter identity and context preservation;
- dependency, Policy, Constraint, Integration, and Legacy isolation; and
- public imports.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
