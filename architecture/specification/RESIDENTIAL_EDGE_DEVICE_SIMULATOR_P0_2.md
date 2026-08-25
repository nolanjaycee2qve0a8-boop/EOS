# Residential Edge Device Simulator — P0.2

## Scope

P0.2 is a deterministic virtual PCS/BMS plant and fault-injection bench above
the P0.1 contracts. It does not modify frozen Strategy, MPC, optimizer,
physical revision, Feasibility, Actuation, Simulator, ledger, acceptance or
Campaign A-F behavior.

```text
P0.1 contracts
        ↑
P0.2 deterministic virtual PCS/BMS + fault injection
        ↑
P0.3 future controlled Runtime loop
```

## Evidence chain

```text
raw virtual PCS/BMS facts
→ P0.1 telemetry / capability / health
→ P0.1 safety decision
→ final software-safe request
→ virtual PCS acknowledgement
→ virtual PCS actual response
→ actual telemetry and P0.1 lifecycle completion or refusal
```

Command is an intent, ACK is a receipt fact and actual telemetry is the only
P0.2 execution fact. An accepted ACK never proves actual power or completion.
P0.2 applies a deliberately fail-closed simulator policy: only an accepted ACK
received exactly at the current step start and strictly before command expiry
may drive that step's virtual PCS response. Rejected, dropped, delayed or
expired ACKs produce normalized `0.0` actual power and no command-driven SOC
change. One immutable `command_application_authorized` fact is calculated once
and drives actual response, SOC progression, lifecycle execution and completion
eligibility together. This is P0.2 test-simulator policy, not a claim about
every real PCS protocol: a real device can receive and execute a command while
its ACK is delayed or lost. Future Runtime therefore must treat actual telemetry
as execution authority and reconcile this uncertainty; P0.2 does not implement
that production reconciliation.

## Time, power and SOC

All scenario steps start from an explicit aware `VirtualClock` time and advance
by a strictly positive caller-supplied duration. Positive kW charges, negative
kW discharges and zero is software `SAFE_IDLE`.

For a duration `Δt` in hours and actual power `P` in kW, stored-energy change
is `P × Δt × η_charge` when `P >= 0`, and `P × Δt / η_discharge` when `P < 0`.
SOC change is stored-energy change divided by `capacity_kwh`. P0.2 limits
actual power before integration so SOC cannot cross configured min/max bounds;
the retained evidence names the affected boundary. This is an interface-level
logical plant, not an electrochemical battery model.

## Fault and recovery rules

Fault schedules are immutable and sorted by `(activation_at, target,
fault_type, fault_id)`. Faults can change raw capabilities, freshness,
connection/health, E-stop, ACK behavior or actual PCS response. The schedule
does not depend on input-list iteration order.

Each public fault has an explicit target and parameter whitelist. Derating and
actual-deviation faults require `factor ∈ [0, 1]`; delayed ACK requires
`seconds ≥ 0`; all other faults accept no parameters. Unsupported target,
missing, extra or invalid parameters are rejected before schedule entry.
`WARNING_FAULT` is retained as a P0.1 warning event without blocking power;
`CRITICAL_FAULT` remains fail-closed.

P0.2 is discrete-time: each step samples its schedule only at `started_at`.
The active interval is `[activation_at, clear_at)`: activation at step start is
active, clear at step start is inactive, and changes inside an interval first
affect the next caller-driven step. This is not a continuous-time hardware model.

Clearing a fault only permits a later caller-supplied new command to be
evaluated. P0.2 never automatically replays, resends, revives or restores an
old command; P0.1 terminal and transition guards remain authoritative.

## Exclusions

No production Runtime loop, real adapter, protocol, hardware/device I/O, HIL,
functional-safety certification, field test or customer deployment claim is
made by P0.2.
