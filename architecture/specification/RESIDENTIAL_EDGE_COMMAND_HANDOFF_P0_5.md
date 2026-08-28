# Residential Edge Command Handoff — P0.5

P0.5 is a pure, caller-driven handoff boundary:

```text
FeasibleDecision + caller-owned EdgeCommandMetadata
        -> unexecuted edge-power-command/v1 PowerCommand
```

`EMSDecision` is a raw strategy request, while `FeasibleDecision` is the only
valid P0.5 power source. P0.5 maps approved charge to positive kW, approved
discharge to negative kW, and approved idle to `0.0`; non-zero commands use
`normal`, while zero uses `safe_idle`.

`EdgeCommandMetadata` is caller-owned identity/time evidence. It has no power
or operating-mode field and never creates UUIDs, sequences, wall-clock times or
TTL values. `EdgeCommandHandoffResult` preserves exact source decision and
metadata identity and verifies every copied PowerCommand metadata field.
For power authority, construction and result validation are intentionally
separate: `EdgeCommandHandoffResult` directly verifies charge/positive/normal,
discharge/negative/normal, and idle/zero/safe-idle from `FeasibleDecision`.
It does not reuse the generator's mapping helper.

P0.5 does not admit, send, execute, retry or replay a command. It does not call
P0.3 tick, P0.2 Simulator, P0.4 Device Adapter, safety, lifecycle, ACK, SOC or
actual telemetry. A future P0.6 may explicitly compose this caller-owned
command with P0.3 admission/safety/runtime and P0.4 adapter evidence.

`ActuationHandoffResult` remains a separate EMS-to-Simulator artifact and is
not a PowerCommand source. Residential EMS 1.0 frozen control semantics and
Campaign A–F results are unchanged.
