# ADR-092 — Residential Edge Command Handoff

## Decision

Add a stateless adapter in `ems_strategy.edge_command_handoff`, not in the
Edge core. The adapter consumes exact `FeasibleDecision` evidence and explicit
caller metadata, then constructs the existing `edge-power-command/v1`
`PowerCommand` contract. `edge_runtime` therefore remains independent of EMS.

## Authority boundary

Approved Feasibility action/power is the sole P0.5 power authority. Metadata is
the sole identity/time authority. Neither raw `EMSDecision`, MPC action,
optimizer output nor Simulator actuation may be converted directly. The result
is an unexecuted command fact, not P0.3 admission or P0.2 execution authority.
The generator may map approved power for construction, but the result contract
independently rereads the approved action, magnitude and command mode/power.
It deliberately does not reuse the generator mapping helper, so a generator
common-mode sign or raw-power defect is rejected before handoff returns.

## Consequences

P0.5 deliberately introduces no protocol, network, thread, scheduler,
persistence, HIL, PCS/BMS/STM32/DSP communication or hardware safety claim.
P0.3 remains caller-command-only. P0.4 owns the separate transport-neutral
Device Adapter boundary, and P0.6 remains deferred.
