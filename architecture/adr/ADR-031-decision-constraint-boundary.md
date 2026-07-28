# ADR-031 ? Decision Constraint Boundary

## Status

Accepted

## Context

`DecisionIntent` expresses semantic policy intention without device commands
or execution behavior. A future executable-decision layer needs an explicit
architectural seam at which constraints can be evaluated without moving that
responsibility into policy intent, runtime, or device adapters.

TASK-032 must establish that seam without choosing constraints or implementing
their evaluation.

## Decision

Introduce:

~~~python
class DecisionConstraintBoundary(ABC):
    def evaluate(
        self,
        intent: DecisionIntent,
    ) -> FeasibleDecisionIntent: ...
~~~

The interface is stateless and has empty slots.

Introduce `FeasibleDecisionIntent` as a frozen, slotted wrapper containing the
exact original `DecisionIntent` reference. The wrapper represents an intent
accepted by a future constraint implementation. It contains no command, event,
calculation detail, or execution state.

## Architecture

~~~text
DecisionIntent
        |
        v
DecisionConstraintBoundary
        |
        v
FeasibleDecisionIntent
        |
        v
Future Executable Decision Generation
~~~

## Consequences

- Constraint evaluation gains a stable dependency-inversion boundary.
- Intent identity and immutability remain intact.
- Future implementations can define explicit constraint sources and
  infeasibility behavior in separate architecture tasks.
- Runtime, dispatch, device, persistence, and telemetry layers remain
  independent.

## Rejected Alternatives

- Add constraints to `DecisionIntent`: rejected because intention and
  constraint evaluation are separate responsibilities.
- Implement SOC or power-limit logic now: rejected because TASK-032 defines
  only an architectural seam.
- Clip battery power automatically: rejected because hidden correction would
  change policy intent.
- Generate a command from the feasible wrapper: rejected because command
  generation is a later layer.
- Add optimization or forecast dependencies: rejected because analytical
  engines do not belong to this boundary.

## Non-goals

- EMS algorithms, strategies, or optimization objectives.
- SOC control, power clipping, or physical modeling.
- Commands, protocols, dispatch, or device execution.
- Runtime state, persistence, telemetry, cache, or history.
