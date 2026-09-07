# Residential Edge P0.8 Validation — Adapter Conformance Harness

> **MERGED STATUS — P0.8.** The strictly limited test-only implementation merged
> through PR #200 into main as `3ba8480203fc4b16e5cd18ca8ed00d4d1556205a` at
> 2026-09-07T04:21:48Z; Quality checks completed SUCCESS. This merge grants no
> production capability, physical device execution, HIL, field readiness, or
> hardware safety claim.

## Current validation purpose

The current test-only, caller-driven, transport-neutral implementation validates
a deterministic scripted adapter
transcript against the frozen P0.7 and P0.6 evidence contracts. It would not
add a real device adapter, command authority, runtime authority, or transport
authority. Scripted transcript facts, ACKs, actuals, history, receipts, and
serialized evidence must remain non-executable audit facts.

## Implemented focused matrix; local terminal evidence recorded

| Case | Implemented focused behavior |
| --- | --- |
| Normal transcript | One caller-approved decision and fresh metadata retain P0.5-to-P0.3 lineage; the scripted observation, one transmission, ACK, and actual facts are traceable without manufacturing authority. |
| Non-admission | A non-admitted P0.7/P0.6 path has no successful transmitted-cycle verdict, no replacement command, and no replay. |
| Unavailable or malformed facts | Explicit unavailable or malformed transcript facts fail closed; they do not mean zero power, success, completion, or recovery. |
| ACK correlation | ID, sequence, and correlation mismatch reject the verdict; an ACK never proves physical execution. |
| Actual comparison | Scripted P0.4 actual is compared as an adapter fact and never replaces P0.3 retained actual/reconciliation. |
| Transcript order | Observation precedes any admitted transmission; ACK/actual facts correspond to that explicit attempt; duplicate or out-of-order facts fail closed. |
| Exact-once | A valid admitted transcript represents one P0.5 handoff, one P0.3 tick/admission, and one P0.4 transmission; the harness adds no second execution. |
| Fresh recovery | A terminal/unavailable case cannot resume from history; any recovery uses P0.7's explicit fresh-session contract, not a harness retry. |
| Authority negatives | Equal-but-distinct source/metadata, historical receipt/transcript, or copied/serialized evidence cannot obtain command or continuation authority. |

The matrix describes merged behavior and its validation evidence. Independent
publication review, PR #200, remote Quality checks SUCCESS, and merge are
complete; none of those facts claims hardware readiness.

## Local mutation evidence

Four isolated mutations removed transcript-order, ACK-correlation,
P0.3/P0.4 fact-separation, and terminal-consumption guards. Each was killed
through public harness composition or a corrupted producer with an independent
validator; manually constructed final failure objects and producer/validator
common-mode self-certification remain unacceptable evidence.

## Local regression evidence and remaining publication sequence

Local evidence completed the following sequence:

```text
P0.8 focused tests
→ P0.1–P0.7 focused and frozen-path regression
→ all edge-runtime tests and Residential frozen regression
→ Campaign A–F regression
→ full pytest with a terminating summary and exit code
→ static, import, sensitive-data, generated-output, and transport scans
→ isolated mutation evidence
→ pre-commit
```

Independent publication review, user-approved PR #200, remote Quality checks
SUCCESS, and merge are complete. This merged evidence does not authorize
network/protocol/Modbus/CAN/serial work,
threads, schedulers, persistence, clock services, auto-retry, HIL, PCS/BMS
connectivity, DSP/STM32 integration, field deployment, or hardware safety
certification.
