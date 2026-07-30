# TASK-045 - EMS Capability Layer Boundary

## Status

IN REVIEW

## Objective

Introduce the first Phase 3 extension boundary for EMS business capabilities.

An EMS capability observes one immutable `DecisionContext` and returns one
semantic `DecisionIntent`. It defines where future business objectives may be
implemented without changing the stable Kernel, Policy, Constraint, Evaluation,
Runtime, or Execution contracts.

TASK-045 defines the boundary only. It implements no EMS capability algorithm.

## Architecture

~~~text
DecisionContext
        |
        v
EMSCapabilityBoundary
        |
        v
DecisionIntent
        |
        v
future constraint and evaluation composition
~~~

The accepted DecisionContext Policy path remains unchanged:

~~~text
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextResult(DecisionIntent)
~~~

TASK-045 does not connect, adapt, replace, or overload that path. Future
composition requires a separate reviewed task.

## Public Contract

~~~python
class EMSCapabilityBoundary(ABC):
    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        context: DecisionContext,
    ) -> DecisionIntent:
        raise NotImplementedError
~~~

The public import is:

~~~python
from capability import EMSCapabilityBoundary
~~~

The package exports only `EMSCapabilityBoundary`.

## Responsibility

A future concrete capability may use decision facts to express one business
objective as a `DecisionIntent`.

Examples of future capability categories may include self-consumption,
time-of-use, peak management, or other reviewed business objectives. These are
examples of extension categories only; TASK-045 implements none of them.

## Statelessness

The abstract boundary:

- is abstract;
- uses empty slots;
- owns no mutable fields;
- owns no cache or history;
- owns no runtime, dispatcher, device, or persistence state; and
- does not mutate `DecisionContext`.

No frozen dataclass is introduced because the boundary is an abstract,
fieldless behavior contract rather than a data model.

## Boundary Separation

Capability is responsible for semantic business intent.

Capability is not responsible for:

- SOC or reserve-SOC enforcement;
- charge or discharge power limits;
- grid import or export limits;
- constraint ordering or explanation;
- PCS or BMS control;
- command generation or dispatch;
- runtime progression;
- persistence or telemetry; or
- optimization or forecasting behavior in this task.

Those concerns remain in their accepted boundaries or require future explicit
architecture decisions.

## Existing Contract Stability

TASK-045 does not modify:

- `DecisionIntent`;
- `DecisionContext`;
- `DecisionContextPolicy`;
- `DecisionContextResult`;
- `DecisionConstraintBoundary`;
- `ConstraintEvaluationPipeline`;
- `DecisionEvaluationCycle`;
- `DecisionEvaluationIntegration`;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Non-goals

- Concrete EMS capability implementation.
- Self-consumption, TOU, peak shaving, zero-export, or pricing algorithms.
- SOC, battery power, or grid limit enforcement.
- Optimization, MPC, or forecasting.
- Runtime, command generation, dispatch, PCS/BMS, or device control.
- Persistence, telemetry, cache, history, scheduling, or retries.
- Migration or adaptation of the existing Policy path.

## Tests

Focused tests cover:

- abstract boundary behavior;
- exact `evaluate(context) -> DecisionIntent` signature;
- exact context and returned intent identities in a test-only implementation;
- empty slots and no instance dictionary;
- no mutable boundary state;
- independence from `DecisionContextPolicy`;
- dependency isolation; and
- exact public export.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
