# TASK-124 - MPC Decision Explanation Formatter

## Objective

Present one exact TASK-123 `MPCDecisionExplanation` as deterministic,
human-readable plain text for diagnostics, CLI, logs, and future API/UI use.

## Contracts

`MPCDecisionExplanationFormatInput` retains the exact machine explanation and
one supported locale (`zh-CN` or `en-US`).
`FormattedMPCDecisionExplanation` retains the exact format-input identity and
non-empty output text. The formatter boundary is abstract and stateless.

## Semantics

The fixed section order shows final decision, original candidate, revision,
candidate evidence, SOC trajectory, power limits, and final verification.
It reads candidate-horizon and final-feasibility booleans directly from the
TASK-123 read model; it never recomputes a physical fact. Numbers are formatted
only for display: power uses up to three decimals and SOC uses two percent
decimals.

## Responsibility separation

```text
PhysicallyAwareMPCCycleResult
    -> MPCDecisionExplanation
    -> FormattedMPCDecisionExplanation
    -> future log / CLI / API / UI
```

Formatting is not optimization, explanation inference, constraint evaluation,
AI generation, or execution.

## Non-goals

No optimizer, projector, evaluator, MPC cycle, Simulator, Actuation, Runtime,
Device, Command, filesystem, logging side effect, network, cache, or template
engine.
