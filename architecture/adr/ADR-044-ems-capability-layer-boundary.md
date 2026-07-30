# ADR-044 - EMS Capability Layer Boundary

## Status

Accepted

## Context

TASK-001 through TASK-044 established a stable Decision Kernel, physical
constraint framework, intent lineage, ordered explanation evidence, and one
complete decision evaluation integration.

EOS now needs an explicit Phase 3 extension seam for business capabilities.
Without a separate seam, future business objectives could be embedded directly
in Policy, Constraint, Runtime, or device code. That would mix semantic intent,
physical feasibility, lifecycle ownership, and external control.

The Kernel must remain stable while capabilities evolve.

## Decision

Introduce an independent top-level capability contract:

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

The boundary receives the exact immutable `DecisionContext` supplied by its
caller and returns one `DecisionIntent`.

TASK-045 introduces no concrete capability and no automatic connection to the
existing `DecisionContextPolicy` or `DecisionEvaluationIntegration`.

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
future reviewed composition
~~~

The existing Policy path remains:

~~~text
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextResult(DecisionIntent)
~~~

The two boundaries are independent. Coexistence does not imply inheritance,
adaptation, delegation, or migration.

## Responsibility

The capability boundary answers one question:

> Given the immutable facts visible to this decision, what semantic business
> intent does this capability express?

It does not answer whether the intent is physically feasible or how it is
executed.

## Statelessness

`EMSCapabilityBoundary` is an abstract fieldless class with empty slots.

It owns no:

- policy instance;
- constraint instance;
- runtime or execution object;
- dispatcher or device object;
- mutable collection;
- cache or history;
- persistence or telemetry client; or
- clock, scheduler, queue, or thread.

A frozen dataclass is not applicable because TASK-045 adds no data carrier.
Future capability parameters require their own explicit immutable contracts.

## Dependency Direction

The capability package may depend on stable decision data contracts:

~~~text
capability -> DecisionContext
capability -> DecisionIntent
~~~

Forbidden directions include:

~~~text
capability -> runtime
capability -> execution
capability -> dispatch
capability -> device protocol
kernel -> capability
~~~

The Kernel does not import the evolving capability package.

## Existing Contract Stability

The following remain unchanged:

- `DecisionIntent`;
- `DecisionContextPolicy`;
- `DecisionContextResult`;
- `DecisionConstraintBoundary`;
- `ConstraintEvaluationPipeline`;
- `ConstraintExplanationChain`;
- `DecisionEvaluationCycle`;
- `DecisionEvaluationIntegration`;
- legacy EMS contracts; and
- runtime and execution paths.

## Consequences

- Phase 3 has an explicit business capability extension point.
- Future capabilities can evolve without modifying Kernel architecture.
- Capability intent remains separate from physical feasibility.
- Runtime and device execution remain outside capability ownership.
- A future task must explicitly define any capability-to-policy or
  capability-to-evaluation composition.

## Rejected Alternatives

- Make capabilities inherit `DecisionContextPolicy`: rejected because TASK-045
  introduces an independent seam and does not migrate Policy.
- Return `DecisionContextResult`: rejected because the capability contract
  expresses semantic intent directly and must not redefine Policy output.
- Put capability methods on `DecisionContext`: rejected because immutable facts
  must not own business behavior.
- Put capability behavior in Constraint: rejected because Constraint determines
  physical feasibility rather than business objectives.
- Connect capability directly to runtime or devices: rejected because intent is
  not execution.
- Add a concrete EMS algorithm now: rejected because this task is boundary-only.

## Non-goals

- EMS strategy implementation.
- Optimization, MPC, forecasting, TOU, pricing, or scheduling.
- SOC, battery power, or grid constraint enforcement.
- Runtime, dispatch, commands, PCS/BMS, or device control.
- Persistence, telemetry, cache, history, retry, or rollback.
- Policy or evaluation integration.
