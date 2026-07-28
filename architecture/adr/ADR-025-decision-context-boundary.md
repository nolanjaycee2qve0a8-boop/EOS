# ADR-025 — Decision Context Boundary

## Status

Accepted

## Context

Future EMS policies need one explicit input boundary describing the facts
available at a decision instant. Passing unrelated scalar arguments would make
the policy contract unstable and obscure which observation set produced a
decision.

The input boundary must remain separate from runtime evidence collection,
policy evaluation, optimization, and decision output.

## Decision

Introduce `DecisionContext` in `kernel.decision` as a frozen, slotted dataclass.

The initial model contains a timezone-aware timestamp and scalar facts for
battery state and capability, power observations, grid price, reserve SOC, and
export limit.

All numeric facts are finite and non-boolean. SOC values use the inclusive
zero-to-one interval. Capacity is positive, while physical limits and
non-negative measurements are non-negative. Grid power and electricity price
are signed observations.

The model owns no mutable collection and defines no behavior beyond factual
input validation.

## Architecture

~~~text
Runtime evidence layer
        |
        v
Decision context layer
        |
        v
Future EMS policy layer
~~~

TASK-026 does not connect this model to runtime, policy, audit, trace, or
explanation objects. Those existing boundaries remain unchanged.

## Identity Preservation

Downstream consumers must retain the exact `DecisionContext` object they
receive. They must not copy, serialize, or reconstruct it. This allows future
explanation boundaries to reference the same context object that a policy
observed.

## Consequences

- Future policies gain a stable immutable input model.
- Input facts are explicit and independently testable.
- Context construction has no runtime or external side effects.
- Policy evaluation and `DecisionResult` remain separate.
- Evidence assembly and explanation integration remain future work.

## Rejected Alternatives

- Add policy methods to the context: rejected because facts do not decide.
- Include commands or optimization results: rejected because those are output.
- Add forecasts or recommendations: rejected because they are derived inputs
  or analysis outside this first boundary.
- Modify runtime or explanation now: rejected because integration is explicitly
  outside TASK-026.
