# ADR-048 - Self Consumption Capability

## Status

Accepted

## Context

TASK-045 established the independent EMS capability extension boundary.
TASK-046 added TOU as the first concrete capability. TASK-047 and TASK-048 then
defined composition and future resolution seams without adding arbitration.

EOS now needs a second concrete capability to demonstrate that different
business objectives can independently produce candidate intents from the same
immutable `DecisionContext`.

Instantaneous PV self-consumption is the smallest useful rule: use PV surplus
as charging intent and load deficit as discharging intent. Physical feasibility
must remain outside the capability.

TASK-037 already contains `SelfConsumptionPolicy`. Reusing that policy directly
would couple the capability layer to a separate accepted policy extension
contract.

## Decision

Introduce:

~~~python
class SelfConsumptionCapability(EMSCapabilityBoundary):
    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionIntent:
        return DecisionIntent(
            battery_power_intent_kw=(context.pv_power_kw - context.load_power_kw),
        )
~~~

The capability validates only that `context` is a `DecisionContext`.

## Physical Contract

Both input facts are literal unscaled kW values:

- `pv_power_kw`: non-negative instantaneous PV generation;
- `load_power_kw`: non-negative instantaneous load consumption.

The output is:

~~~text
battery_power_intent_kw = pv_power_kw - load_power_kw
~~~

Under the existing `DecisionIntent` sign convention:

- positive means battery charging intent;
- negative means battery discharging intent; and
- zero means idle.

No unit conversion, scaling, clipping, saturation, or rounding is performed.

## Architecture

~~~text
DecisionContext
        |
        v
SelfConsumptionCapability
        |
        v
DecisionIntent candidate
        |
        v
Future Composition / Resolution
        |
        v
Constraint Layer
~~~

TASK-049 creates only the capability and its returned intent. It does not run
composition, resolution, constraints, evaluation, runtime, or devices.

## Fact Ownership

The capability reads only PV and load.

It intentionally ignores:

- timestamp and electricity price;
- SOC and reserve SOC;
- battery power limit and energy capacity;
- grid power and export limit; and
- all runtime, device, and communication state.

These facts cannot alter the basic self-consumption candidate intent.

## Constraint Separation

The complete instantaneous PV-load difference is emitted even when:

- SOC is full or at reserve;
- the battery power limit is zero;
- grid limits would be exceeded; or
- device capability differs.

Battery and Grid Constraint implementations remain responsible for producing
physical feasibility. The capability performs no zero-export control.

## Policy Coexistence

`SelfConsumptionPolicy` and `SelfConsumptionCapability` remain independent:

~~~text
DecisionContext -> SelfConsumptionPolicy -> DecisionContextResult
DecisionContext -> SelfConsumptionCapability -> DecisionIntent
~~~

TASK-049 introduces no inheritance, adapter, call, migration, alias, or shared
mutable implementation between them. Existing Policy and legacy paths remain
unchanged.

## Statelessness

`SelfConsumptionCapability` is fieldless and empty-slotted. It stores no
context, intent, parameters, cache, history, runtime state, or external
dependency.

No frozen dataclass is needed because no data carrier is introduced.

## Dependency Direction

Allowed:

~~~text
capability.self_consumption -> capability.base
capability.self_consumption -> kernel.decision
~~~

Forbidden:

~~~text
kernel -> capability.self_consumption
capability.self_consumption -> policy
capability.self_consumption -> constraint / evaluation
capability.self_consumption -> runtime / execution / dispatch
capability.self_consumption -> device / persistence / telemetry
~~~

## Existing Contract Stability

The following remain unchanged:

- `DecisionIntent` and its battery power sign convention;
- `EMSCapabilityBoundary`;
- capability composition and intent resolution boundaries;
- TOU capability;
- Policy contracts and `SelfConsumptionPolicy`;
- Constraint contracts and implementations;
- Evaluation Integration and Cycle;
- legacy EMS contracts; and
- runtime and execution paths.

## Consequences

- EOS gains a second concrete EMS capability.
- Capability composition can later observe TOU and self-consumption candidates
  independently.
- Self-consumption intent remains deterministic and explainable.
- Physical feasibility stays in Constraint.
- No current evaluation or runtime path changes.

## Rejected Alternatives

- Call `SelfConsumptionPolicy`: rejected because Capability and Policy are
  independent extension boundaries.
- Share a mutable helper object: rejected because the arithmetic is one
  explicit domain formula and no state is required.
- Enforce SOC or battery power: rejected because Constraint owns feasibility.
- Use grid power or export limit: rejected because that would introduce grid
  or zero-export behavior.
- Use price or time: rejected because TOU is an independent capability.
- Generate commands: rejected because capabilities produce semantic intents.

## Non-goals

- SOC, battery power, Grid, or zero-export enforcement.
- TOU, pricing, optimization, MPC, forecasting, or scheduling.
- PCS/BMS, communication protocol, runtime, dispatch, or device control.
- Composition or resolution execution.
- Persistence, telemetry, cache, or history.
