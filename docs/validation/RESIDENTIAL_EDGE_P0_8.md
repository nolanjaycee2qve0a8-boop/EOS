# Residential Edge P0.8 Validation — Adapter Conformance Harness Candidate

> **DRAFT — P0.8 candidate only.** This plan requires a subsequent user scope
> decision. No production implementation is authorized. It is not a claim of
> physical device execution, HIL, field readiness, or hardware safety.

## Candidate validation purpose

If implementation is later approved, this test-only, caller-driven,
transport-neutral candidate would validate a deterministic scripted adapter
transcript against the frozen P0.7 and P0.6 evidence contracts. It would not
add a real device adapter, command authority, runtime authority, or transport
authority. Scripted transcript facts, ACKs, actuals, history, receipts, and
serialized evidence must remain non-executable audit facts.

## Proposed focused matrix

| Candidate case | Future fact to prove |
| --- | --- |
| Normal transcript | One caller-approved decision and fresh metadata retain P0.5-to-P0.3 lineage; the scripted observation, one transmission, ACK, and actual facts are traceable without manufacturing authority. |
| Non-admission | A non-admitted P0.7/P0.6 path has no successful transmitted-cycle verdict, no replacement command, and no replay. |
| Unavailable or malformed facts | Explicit unavailable or malformed transcript facts fail closed; they do not mean zero power, success, completion, or recovery. |
| ACK correlation | ID, sequence, and correlation mismatch reject the candidate verdict; an ACK never proves physical execution. |
| Actual comparison | Scripted P0.4 actual is compared as an adapter fact and never replaces P0.3 retained actual/reconciliation. |
| Transcript order | Observation precedes any admitted transmission; ACK/actual facts correspond to that explicit attempt; duplicate or out-of-order facts fail closed. |
| Exact-once | A valid admitted transcript represents one P0.5 handoff, one P0.3 tick/admission, and one P0.4 transmission; the harness adds no second execution. |
| Fresh recovery | A terminal/unavailable case cannot resume from history; any recovery uses P0.7's explicit fresh-session contract, not a harness retry. |
| Authority negatives | Equal-but-distinct source/metadata, historical receipt/transcript, or copied/serialized evidence cannot obtain command or continuation authority. |

These are future acceptance cases, not tests that have run or passed.

## Proposed mutation evidence

Future mutation work, if authorized, would run only in isolated temporary
worktrees and must record the actual test node and failed independent assertion.
The planned mutations are removal of transcript-order, ACK-correlation,
P0.3/P0.4 fact-separation, and terminal-consumption guards. Each must be killed
through the public candidate composition or a corrupted producer and an
independent validator; manually constructed final failure objects and
producer/validator common-mode self-certification are not acceptable evidence.

## Conditional regression and publication sequence

Any future implementation would require, in order:

```text
P0.8 focused tests
→ P0.1–P0.7 focused and frozen-path regression
→ all edge-runtime tests and Residential frozen regression
→ Campaign A–F regression
→ full pytest with a terminating summary and exit code
→ static, import, sensitive-data, generated-output, and transport scans
→ isolated mutation evidence
→ pre-commit
→ independent review
→ explicit user-approved PR, CI, and merge
```

This DRAFT neither implements the harness nor reports any result from that
sequence. It does not authorize network/protocol/Modbus/CAN/serial work,
threads, schedulers, persistence, clock services, auto-retry, HIL, PCS/BMS
connectivity, DSP/STM32 integration, field deployment, or hardware safety
certification.
