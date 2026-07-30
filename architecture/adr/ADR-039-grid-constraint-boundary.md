# ADR-039 - Grid Constraint Boundary

## Status

Accepted

## Context

EOS now distinguishes the immutable policy source intent from the feasible
intent produced by physical constraint evaluation. TASK-038 supplied the first
battery constraint implementation, and TASK-039 stabilized that lineage.

Grid-side feasibility is a separate physical concern. Future capabilities may
need import limits, export limits, or zero-export enforcement, but placing
those concerns in policy, the battery constraint, the general constraint
contract, or runtime would couple unrelated responsibilities.

TASK-040 needs an explicit grid-specific extension point without selecting or
implementing a grid constraint algorithm.

## Decision

Introduce:

~~~python
class GridConstraintBoundary(DecisionConstraintBoundary):
    @abstractmethod
    def evaluate(
        self,
        intent: DecisionIntent,
    ) -> FeasibleDecisionIntent: ...
~~~

The boundary is abstract, stateless, and uses empty slots. Its method signature
is identical to the existing `DecisionConstraintBoundary` contract.

The abstract type contains no limit values or capability flags. Future concrete
implementations may receive explicitly defined immutable grid facts through
construction, preserving substitutability and keeping grid-specific inputs out
of the general constraint interface.

## Architecture

~~~text
DecisionContextResult.intent
        |
        v
source DecisionIntent
        |
        v
GridConstraintBoundary
        |
        v
FeasibleDecisionIntent
~~~

TASK-040 does not change the source/feasible lineage rules. The boundary only
identifies where future grid feasibility implementations plug in.

## Consequences

- Grid constraints gain an explicit dependency-inversion boundary.
- The general constraint contract remains stable.
- Policy continues to express intention without grid feasibility logic.
- Grid facts remain implementation inputs rather than leaked generic fields.
- Runtime, dispatch, device, persistence, and telemetry remain isolated.
- A later task must define concrete facts, units, ranges, and algorithms.

## Rejected Alternatives

- Add grid arguments to `DecisionConstraintBoundary.evaluate`: rejected because
  it would leak grid-specific facts into every constraint implementation and
  break the existing substitutable contract.
- Put import/export rules in policy: rejected because policy expresses desired
  energy behavior while constraints establish physical feasibility.
- Reuse `BatteryConstraintImplementation`: rejected because battery capability
  and grid interconnection capability have different ownership.
- Implement zero export now: rejected because TASK-040 establishes a boundary,
  not an algorithm.
- Put grid checks in runtime or device adapters: rejected because those layers
  execute or integrate completed decisions rather than define feasibility.

## Non-goals

- Import limiting, export limiting, or zero-export behavior.
- TOU, electricity-price strategy, optimization, or forecasting.
- PCS control, commands, protocols, dispatch, or runtime execution.
- Persistence, telemetry, cache, history, or mutable state.
- Legacy `EMSPolicy` or `DecisionResult` migration.
- Changes to `DecisionIntent`, `DecisionConstraintBoundary`, or intent lineage.
