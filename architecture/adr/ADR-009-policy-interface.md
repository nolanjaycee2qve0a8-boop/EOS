# ADR-009 — EMS Policy Interface Boundary

## Status

Accepted

## Context

Future EMS algorithms require a stable extension boundary. Without a dedicated
contract, energy-management logic could become embedded in runtime components,
coupled to infrastructure, or hardcoded as one non-replaceable strategy.

EOS already has immutable EnergySystemContext and DecisionResult models. It
also has an earlier DecisionPolicy contract for Snapshot and Mission inputs.
The EMS boundary has a distinct domain input and must not silently alter that
existing contract.

## Decision

Introduce EMSPolicy as an abstract, stateless interface with one method:

`evaluate(context: EnergySystemContext) -> DecisionResult`

Implementations are required to be deterministic and side-effect free. They
must not mutate the context or any aggregated asset, state, or PowerFlow. They
must not own clocks, schedulers, threads, storage, communication, or device
access.

Use `evaluate` rather than overloading the existing
`DecisionPolicy.decide(snapshot, mission)` name. Keep DecisionPipeline
independent and defer any integration or adaptation to a separate architecture
decision.

## Consequences

- Future EMS algorithms can be replaced behind one stable interface.
- DecisionPipeline and runtime remain independent from EMS implementation details.
- Immutable inputs and outputs support deterministic policy testing.
- Infrastructure ownership remains outside policy implementations.
- A future task must explicitly define orchestration between EMSPolicy and runtime.

## Alternatives Considered

- Embedding EMS logic in runtime: rejected because runtime owns transitions and
  must remain independent from evolving capabilities.
- Hardcoding one EMS algorithm: rejected because strategies must be replaceable.
- Mutable policy behavior: rejected because hidden state undermines replay and
  deterministic evaluation.
- Reusing the existing DecisionPolicy method unchanged: rejected because its
  Snapshot and Mission inputs do not represent EnergySystemContext.
- Adding a concrete no-op or rule-based policy: rejected because TASK-010
  establishes only the interface contract.
