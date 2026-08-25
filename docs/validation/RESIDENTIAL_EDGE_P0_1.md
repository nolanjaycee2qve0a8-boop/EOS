# Residential Edge P0.1 Validation — Runtime Interface and Safety Contracts

## Scope and publication state

P0.1 is local contract validation, not a device, HIL or deployment result. It
adds no Residential EMS 1.0 control capability and keeps the A-F numerical
evidence frozen. Publication occurs only after the separate release workflow;
this document does not imply a pushed branch or merged PR.

## Contract matrix

| Area | Invariant | Negative evidence |
| --- | --- | --- |
| Command | finite signed kW, aware time, stable id, non-negative sequence | NaN/Inf/bool, naive time, invalid window, expired/future command |
| ACK | known command/sequence only; receipt is not completion | unknown, conflicting duplicate and late ACK |
| Telemetry | observed/received facts separate; unknown remains `None` | stale observed value despite fresh receipt, out-of-range SOC, reversed time |
| Capability | BMS and PCS identities retained; effective capability is evaluator-derived | forged permissive effective input, invalid source/window, stale capability, prohibited direction |
| Safety | `READY` only, high authority wins; request is not actual | BMS block, PCS clamp, reserve block, critical fault, emergency stop and unhealthy Runtime |
| Lifecycle | ACK → retained execution start → in-window actual-telemetry completion; terminal cannot reactivate | late ACK, replay, rollback, pre-execution telemetry, expiry crossing, forged hydration and invalid successor |
| Serialization | immutable data schemas are versioned UTC ISO-8601; services are excluded | missing/unknown fields, unsupported schema and invalid payload numeric values |
| Isolation | no transport or frozen-control dependency | AST import test; no adapter is required to run contracts |

## Required acceptance observations

- actual telemetry, not plan/command/ACK, is the execution truth;
- stale telemetry or capability cannot sustain economic active-power requests;
- BMS permission and PCS power capability supersede an EMS request;
- duplicate exact inputs are idempotent while conflicting replay is rejected;
- `ACK_ACCEPTED` remains distinct from `COMPLETED`;
- actual completion telemetry is observed no earlier than `execution_started_at`,
  received no earlier than observed, and all completion facts remain strictly
  before command expiry; an ACK never substitutes for that causal evidence;
- serialized lifecycle records are inspectable evidence only and cannot restore
  an authoritative book; `COMPLETED` without matching actual completion
  evidence is invalid; a successor is a complete command whose sequence is
  higher than the book-global maximum, not an arbitrary identifier;
- supersede failure has no partial write, and the implemented transition matrix
  is guarded only through specialized lifecycle methods, never a generic public
  transition endpoint;
- recovery readiness permits only new commands after full fresh/healthy,
  available, non-emergency, no-critical-fault and quiescent-lifecycle checks;
  it never restores an old command;
- `SAFE_IDLE` is software fail-closed evidence, not hardware protection proof.

## P0.2 and P0.3 inputs

P0.2 may use these contracts for a deterministic device simulator, fault
injection and latency/loss execution. P0.3 may use them for a bounded runtime
cycle, telemetry polling, EMS invocation, command transmission, ACK wait and
durable recovery. Both require separate approval and tests.

## Current limitations

No real adapter, device address, telemetry link, durable store, scheduler,
thread, HIL, PCS/BMS/DSP communication, hardware safety analysis, field test or
standards certification exists in P0.1.
