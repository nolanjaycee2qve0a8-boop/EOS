# ADR-017 — Deterministic Command Executor

## Status

Accepted

## Context

EOS now defines CommandDispatcher as the abstract boundary for submitting one
immutable Command. DecisionResult contains an ordered immutable tuple of
commands, but no kernel boundary owns their deterministic sequential
submission.

Putting orchestration into DecisionResult, a concrete adapter, or the runtime
would mix responsibilities and risk inconsistent ordering or failure behavior.

## Decision

Introduce stateless CommandExecutor with empty slots and one static operation:

`execute(dispatcher: CommandDispatcher, decision_result: DecisionResult) -> None`

Validate both inputs before dispatch. Then visit `decision_result.commands` in
exact tuple order and call the supplied dispatcher once for every position with
the exact stored Command object.

Return None after normal completion. On the first dispatcher exception, stop
immediately and let the exact exception propagate. Do not retry, roll back, or
produce a partial result. Ignore DecisionResult events completely.

## Consequences

- Command ordering and per-position dispatch are deterministic.
- Repeated Command references retain their positional meaning.
- Empty results complete without dispatcher calls.
- Dispatcher failure behavior is explicit and minimal.
- No receipt, status, rollback, retry, or partial-result model is introduced.
- Runtime and immutable decision boundaries remain unchanged.

## Alternatives Considered

- Dispatch directly from DecisionResult: rejected because immutable output
  objects must not own side effects.
- Dispatch in runtime: rejected because runtime integration is outside this
  task and would couple separate boundaries.
- Batch commands through the dispatcher: rejected because it introduces
  ordering and partial-failure semantics.
- Catch and wrap adapter exceptions: rejected because no error translation
  contract exists.
- Return completed and failed commands: rejected because partial execution
  result models are explicitly deferred.
- Retry failures: rejected because retry ownership and timing are undefined.
