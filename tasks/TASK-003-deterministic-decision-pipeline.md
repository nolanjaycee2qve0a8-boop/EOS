# TASK-003 — Deterministic Decision Pipeline

## Status

IN REVIEW

## Objective

Establish the first deterministic execution boundary between immutable EOS
domain data and replaceable decision logic.

## Scope

- A runtime-checkable structural `DecisionPolicy` contract.
- An immutable `DecisionResult` carrying ordered Commands and Events.
- A synchronous `DecisionPipeline` that validates contracts and invokes one
  policy exactly once.
- Deterministic unit tests and stable public imports.

## Non-goals

- Runtime or background loops.
- EMS scheduling, optimization, forecasting, or production policies.
- Event Journal, replay implementation, persistence, or publication.
- APIs, networking, hardware communication, async execution, or retries.

## Architecture

`DecisionPolicy` contains decision logic and receives only a `Snapshot` and a
`Mission`. `DecisionPipeline` is an orchestration boundary that makes exactly
one policy call. `DecisionResult` defensively stores the resulting Commands
and Events as tuples.

TASK-003 deliberately does not implement a runtime loop or Event Journal.

## Acceptance Criteria

- Policies are structurally replaceable without inheriting a framework class.
- Result collections are validated, defensively copied, ordered, and immutable.
- The pipeline validates inputs and outputs, calls once, and preserves identity.
- Policy exceptions remain visible to the caller.
- TASK-002 behavior and public imports remain unchanged.
- All local checks and GitHub Actions pass.

## Validation Commands

```bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
```

## Implementation Notes

The pipeline does not read a clock, generate IDs, mutate inputs, create output
objects, reorder results, retry failures, or perform I/O. Test policies remain
local to the test suite; no production EMS policy or registry is introduced.
