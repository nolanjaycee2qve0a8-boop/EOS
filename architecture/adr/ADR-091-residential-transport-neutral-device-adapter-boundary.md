# ADR-091 — Residential Transport-Neutral Device Adapter Boundary

P0.4 introduces a fact-only port between future PCS/BMS I/O implementations
and the frozen P0.1–P0.3 semantics. It is neither a controller nor a protocol
implementation: no Modbus, CAN, serial, network, thread, scheduler, HIL,
persistence, wall clock or hardware-control capability is introduced.

The port keeps four operations separate: acquire observation, transmit one
already-authorized safe request, observe ACK, and observe actual telemetry.
ACK is not actual execution, and actual telemetry has no invented command
correlation. Observation timestamps remain explicit P0.1 input; P0.4 never
declares a latest value fresh.

`DeviceTransmissionRequest` is an in-process one-shot carrier. It may only be
constructed from the exact current P0.3 caller/admitted command identity and
its `SafetyDecision`; it retains transport fields, not a `PowerCommand`. It is
non-copyable and non-serializable. Serialized P0.4 records are audit evidence
only and cannot hydrate an adapter, Runtime, lifecycle, prepared simulator or
retry authority. A request remains consumed even if a scripted adapter is
recreated, so failure, polling and reconstruction never replay it.

The included scripted adapter is deterministic contract infrastructure, not a
second P0.2 plant. It consumes only caller-supplied facts/scripts, attempts
exactly once per request, retains no command cache, and has no clock or retry.
P0.1 owns safety/freshness/lifecycle, P0.2 remains the virtual plant, and P0.3
remains caller-driven. Future real adapters must implement this port without
changing those layers.
