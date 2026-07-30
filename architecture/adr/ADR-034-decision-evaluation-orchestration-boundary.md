# ADR-034 ? Decision Evaluation Orchestration Boundary

## Status

Accepted

## Context

EOS has independent immutable boundaries for physical state, decision context,
policy output, semantic intent, constraint evaluation, explanation, and the
completed evaluation cycle. A caller currently has to compose these contracts
itself, which leaves lifecycle ordering outside a stable kernel boundary.

## Decision

Introduce `DecisionEvaluationOrchestrator` as a stateless coordinator. It
receives `EnergySystemState`, `DecisionContextPolicy`,
`DecisionConstraintBoundary`, and all external decision facts explicitly for
each call.

The orchestrator reuses the existing boundaries in deterministic order:

~~~text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContextPolicy
        |
        v
DecisionConstraintBoundary
        |
        v
ConstraintExplanation
        |
        v
DecisionEvaluationCycle
~~~

It calls each evaluation boundary once, validates returned contract types, and
passes the exact artifacts forward. It does not copy, normalize, reconstruct,
or persist them.

## Identity and Ownership

The returned `DecisionEvaluationCycle` validates the existing identity chain:

~~~python
cycle.source_intent is cycle.result.intent
cycle.explanation.feasible_intent is cycle.feasible_intent
cycle.explanation.source_intent is cycle.source_intent
~~~

The feasible inner intent is the exact constraint output. It may preserve
`cycle.source_intent` identity when unchanged or differ after an immutable
constraint adjustment.

The orchestrator has empty slots. It receives policy and constraint instances
per invocation and retains neither.

## Consequences

- One deterministic composition point now connects existing decision
  contracts.
- External decision facts remain explicit and have no hidden defaults.
- Policy and constraint implementations remain replaceable.
- Failures propagate without advancing later lifecycle stages.
- Device execution and runtime architecture remain separate.

## Rejected Alternatives

- Store policy or constraint instances: rejected because orchestration must be
  stateless.
- Reimplement assembly, policy, constraint, explanation, or cycle logic:
  rejected because the existing boundaries own those contracts.
- Add fallback values or derive missing constraints: rejected because that
  would introduce hidden decision behavior.
- Generate commands or dispatch devices: rejected because execution belongs to
  a future boundary.

## Non-goals

- EMS strategy, optimization, or forecasting.
- Runtime integration or state retention.
- Commands, dispatch, PCS/BMS control, or device protocols.
- Persistence, telemetry, cache, or history.
