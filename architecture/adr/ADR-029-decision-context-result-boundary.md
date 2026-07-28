# ADR-029 ? DecisionContext Result Boundary

## Status

Accepted

## Context

`DecisionContextPolicy` needs an output contract that belongs to the new
decision-context path. The existing `DecisionResult` belongs to the legacy
execution path and contains commands and events consumed by runtime and
dispatch components. Reusing it would couple policy output to execution
artifacts.

TASK-030 does not define policy output fields or command-generation behavior.

## Decision

Introduce `DecisionContextResult` as an independent frozen, slotted dataclass.
TASK-031 subsequently adds its immutable semantic `DecisionIntent` reference.
The result contains no commands, events, mutable collections, cache, or
history.

Change only `DecisionContextPolicy.evaluate()` to return
`DecisionContextResult`. Keep `DecisionResult`, `EMSPolicy`, and all legacy
runtime, execution, cycle, and dispatch consumers unchanged.

## Architecture

~~~text
Legacy:
EnergySystemContext -> EMSPolicy -> DecisionResult -> Execution

New:
DecisionContext -> DecisionContextPolicy -> DecisionContextResult
                                        -> Future command generation layer
~~~

## Consequences

- Policy output is separated from device commands and execution events.
- The new boundary has no runtime, dispatch, persistence, optimization, or
  forecast dependency.
- Legacy execution behavior remains stable.
- Future result fields and command generation require explicit architecture
  decisions.

## Rejected Alternatives

- Reuse legacy `DecisionResult`: rejected because it exposes commands and
  execution events.
- Remove fields from legacy `DecisionResult`: rejected because it would break
  existing consumers.
- Add commands or events to `DecisionContextResult`: rejected because those
  artifacts belong to later layers.
- Invent policy-specific result fields: rejected because TASK-030 defines only
  the boundary.
