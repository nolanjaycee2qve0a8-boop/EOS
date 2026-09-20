# P0.11 Local Validation — Device-Fact Command-Correlation Audit

> **LOCAL IMPLEMENTATION EVIDENCE ONLY / UNPUBLISHED.** This record is neither
> a release claim nor an authorization for device, hardware, transport, or field
> operation.

## Validation question

Can a pure evaluator assess finite caller-owned inert transmission, ACK, actual,
relationship, and assessment-time facts as PASS/GAP without manufacturing
command, replay, transport, execution, reconciliation, or physical-completion
authority?

## Focused contract matrix

| Area | Required local evidence |
| --- | --- |
| Transmission identity | Caller identity, sequence, origin, time, source, and epoch remain inert audit values. |
| ACK correlation | Identity, sequence, origin, time, source, epoch, availability, and explicit relationship mismatch fail closed as GAP. |
| Actual separation | Actual is independent from ACK and cannot cure an ACK GAP or replace P0.3 reconciliation. |
| Relationship | Same source/epoch and explicitly declared cross-source/epoch relationships pass; absent or conflicting relationships GAP. |
| Assessment scope | Reused identity, stale/future time, and historical evidence-as-input fail closed. |
| Authority boundary | Assessment holds no input, command, request, runtime, adapter, session, continuation, or transmission reference. |
| Import boundary | No transport, protocol, thread, persistence, P0.3/P0.4 runtime, P0.9, or P0.10 import is permitted. |

## Local focused command

```powershell
$env:PYTHONPATH = (Get-Location).Path
pytest tests/unit/edge_runtime/test_device_fact_command_correlation.py
```

This focused gate does not replace upstream/frozen regressions, Campaign A–F,
full pytest, pre-commit, independent producer-corruption mutation evidence,
independent review, CI, or a publication decision.

## Required later gate order

```text
focused contract tests
→ upstream / frozen / Campaign A–F regression
→ full pytest with terminal summary and exit code
→ static, import, sensitive-data, generated-output, and pre-commit gates
→ isolated producer-corruption mutation evidence
→ independent read-only review
→ explicit user decision on push / PR / merge
```

P0.11 does not implement or authorize protocols, networking, HIL,
PCS/BMS/DSP/hardware work, field control, or physical-completion claims.
