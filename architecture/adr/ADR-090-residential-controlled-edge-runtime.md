# ADR-090 — Residential Controlled Edge Runtime Prototype

P0.3 composes P0.1 safety/lifecycle with the caller-stepped P0.2 logical
plant.  Every tick is explicit and deterministic: no thread, wall clock,
transport, retry or command replay exists.  The runtime retains command, safe
request, ACK and actual telemetry as separate facts.  ACK is not execution;
actual telemetry is authoritative for reconciliation.  This prototype is not
a production Runtime, HIL result, device adapter or hardware safety claim.

P0.3 prepares exactly one P0.2 session per tick, reads its observation for
readiness, then consumes that session exactly once. It does not expose the
prepared authority to callers; immutable evidence is not execution authority.

## Stage 2A runtime state and admission boundary

P0.3 owns a guarded runtime-state transition table. `STARTING`,
`WAITING_FOR_FRESH_TELEMETRY`, `DEGRADED`, `SAFE_IDLE`, `FAULTED`, and
`SHUTTING_DOWN` never admit a non-zero caller command; only a tick that *began*
in `READY` and has complete readiness may do so. A fresh startup or recovery
observation may transition to `READY`, but is observation-only: a caller command
on that tick is not replayed or executed.

Stale telemetry/capabilities or unknown SOC/actual power map to
`WAITING_FOR_FRESH_TELEMETRY`; connection, availability, channel, runtime-link,
or unresolved lifecycle evidence maps to `DEGRADED`; explicit software fallback,
an ACK rejection, an expired request, or an ordinary safety block maps to
`SAFE_IDLE`; critical faults, E-stop, and an unexpected non-zero actual map to
`FAULTED`. Warning evidence alone remains observable without being reported as a
device fault. Shutdown is explicit and terminal for ordinary ticks.

P0.3 exposes no generic public transition or supersede operation. An in-flight
command prevents new admission until lifecycle expiry/terminal evidence is
visible; a subsequent recovery observation, then a later READY-start tick, may
admit a new increasing sequence. Runtime state and lifecycle state remain
separate evidence.

Every admitted P0.3 command is the exact object supplied by the current
caller-driven `tick` invocation. `tick(None)` admits `None`; trace, lifecycle
records, ACKs, actual telemetry, safety-final requests and recovery/state facts
are audit or reconciliation evidence, never command sources. READY restores
eligibility to receive a new caller command; it never restores prior power,
creates a replacement identity/sequence, retries, resumes or replays history.
After admission selection and before P0.2 `execute`, the current-caller guard
checks object identity. This is an execution-containment boundary: a corrupted
selector result is rejected before it can advance plant clock, SOC, actual
power, lifecycle or authoritative runtime state.

## Stage 2B reconciliation and evidence boundary

P0.3 classifies one completed tick from retained facts rather than treating an
ACK as completion. Its five separate power layers are caller requested power,
safety-final requested power, ACK accepted power, expected actual power, and
Simulator actual telemetry power. The last is the execution-fact authority.
`CommandReconciliation` records all applicable reasons in one stable risk order
and names the first as primary; a compound event retains secondary causes.

`RuntimeLoopTrace`, its step, lifecycle snapshot and reconciliation are frozen,
schema-versioned audit evidence. Strict deserialization validates declared
schema/fields, enums, UTC times, finite numbers and tick/time/state/SOC links.
Each step additionally retains caller command, admitted command, a closed
`current_caller`/`none` origin and an always-false automatic-generation fact so
the command-provenance boundary is auditable. This post-execution trace contract
is a second, audit-layer defense; it neither creates execution authority nor
substitutes for the pre-execution current-caller guard.
It cannot hydrate a runtime, lifecycle book, Simulator or P0.2 prepared
authority; no persistent recovery is provided. This remains deterministic
prototype evidence, not process security, protocol security, hardware authority
or a production Runtime.
