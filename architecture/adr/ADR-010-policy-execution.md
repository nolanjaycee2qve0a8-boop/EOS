# ADR-010 — Stateless Policy Execution Adapter

## Status

Accepted

## Context

EOS now has an immutable EnergySystemContext input, an abstract EMSPolicy
extension boundary, and an immutable DecisionResult output. A narrow adapter is
needed to invoke the policy without introducing runtime ownership, policy
lifecycle state, or algorithm behavior.

Embedding execution directly into runtime would couple stable orchestration to
evolving EMS capabilities. Storing a policy in the adapter would also turn the
adapter into a lifecycle owner rather than a single-call boundary.

## Decision

Introduce PolicyExecutor as a stateless class with a static method:

`execute(policy: EMSPolicy, context: EnergySystemContext) -> DecisionResult`

Validate the policy and context before invocation, call
`policy.evaluate(context)` once, validate the returned DecisionResult, and
return the exact result object.

Do not retain the policy or context. Do not catch or translate policy
exceptions. Do not mutate the context or any nested asset, state, or PowerFlow.

## Consequences

- EMS policies have one explicit, independently testable invocation boundary.
- Callers can replace a policy on every evaluation.
- The adapter remains stateless and policy-lifecycle independent.
- Context immutability and exception identity are preserved.
- Runtime loops and scheduling remain separate future architecture concerns.

## Alternatives Considered

- Store a policy in PolicyExecutor: rejected because the adapter must not own
  policy instances or lifecycle.
- Embed invocation in runtime: rejected because runtime ownership and EMS
  capability evolution must remain separate.
- Catch and wrap policy exceptions: rejected because this boundary has no
  specified error translation model.
- Retry failed policies: rejected because retries require scheduling and runtime
  semantics outside this task.
- Add a concrete EMS algorithm: rejected because policy implementation is a
  separate capability concern.
