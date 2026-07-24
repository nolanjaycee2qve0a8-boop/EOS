# TASK-018 — Deterministic Command Executor

## Status

IN REVIEW

## Objective

Create a stateless deterministic orchestration boundary that submits the
immutable commands in one DecisionResult to one CommandDispatcher.

## Scope

- Add `CommandExecutor.execute(dispatcher, decision_result)`.
- Validate both boundary inputs before any dispatch.
- Dispatch commands sequentially in exact tuple order.
- Preserve every Command identity and tuple position.
- Stop at the first dispatcher exception and propagate it unchanged.
- Ignore DecisionResult events completely.

## Execution Contract

After validating CommandDispatcher and DecisionResult, CommandExecutor visits
each position in `decision_result.commands` in order and calls
`dispatcher.dispatch(command)` exactly once.

Commands are not sorted, deduplicated, grouped, copied, rebuilt, normalized,
transformed, parallelized, batched, or retried. Repeated references are
dispatched once for every tuple position.

An empty command tuple produces no calls and returns None.

## Failure Contract

The first dispatcher exception stops execution immediately. The failed command
is not retried, later commands are not submitted, and earlier completed calls
are not rolled back. The exact exception propagates unchanged and no partial
result is returned.

## Ownership

CommandExecutor has empty slots and retains no dispatcher, DecisionResult,
command, progress, failure, history, receipt, connection, or runtime state.
Events are neither read for behavior nor processed.

## Non-goals

- Concrete dispatchers or Modbus, CAN, MQTT, HTTP, serial, or PCS adapters.
- Runtime integration, batching, parallelism, retries, or timeouts.
- Loops beyond finite command tuple traversal, schedulers, queues, or threads.
- Async execution, rollback, compensation, receipts, or execution status.
- Journaling, persistence, telemetry, clocks, timestamps, or UUID generation.
- Device control, SOC updates, EMS algorithms, optimization, or forecasting.

## Acceptance Criteria

- Inputs are validated before any dispatch.
- Commands dispatch once per tuple position in exact order and identity.
- Empty and successful execution return None.
- First failure stops execution and preserves exception identity.
- Events are ignored.
- CommandExecutor is stateless and publicly exported with CommandDispatcher.
- No concrete production dispatcher is introduced.
- All repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
