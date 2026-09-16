# ADR-099 — P0.11 Candidate: Residential Device-Fact Command-Correlation Audit

> **PLANNING-ONLY / NOT APPROVED FOR IMPLEMENTATION OR RELEASE.** This is a
> prospective candidate contract. It does not create a public API, authorize
> implementation, or establish device, hardware, field, or release readiness.

## Context

P0.9 records whether caller-supplied device-fact evidence can meet declared
readiness semantics. P0.10 records whether a finite caller-supplied sequence
of those facts preserves lifecycle-continuity semantics. Neither stage defines
an audit-only assessment of whether inert caller-declared transmission identity,
ACK correlation, and actual-observation facts are mutually consistent at a
declared assessment identity and `as_of` time.

That prospective gap is an evidence-correlation question. It is not a request
to issue, retransmit, recover, execute, or complete a command. P0.3 retained
actual/reconciliation, P0.4 adapter facts, P0.8 conformance evidence, and
P0.9/P0.10 PASS/GAP assessments keep their existing distinct meanings.

## Candidate decision

If separately authorized in a future stage, P0.11 would assess one finite,
caller-owned set of declared facts:

```text
inert caller transmission identity + declared ACK correlation + actual observation
              + assessment identity / as_of
                                      |
                                      v
             deterministic audit-only correlation assessment
                                      |
                                      v
                     immutable PASS/GAP findings only
```

The prospective input would carry only inert values: a caller-owned
transmission/request identity, declared ACK-correlation facts, a distinct
actual-observation fact, and a caller-owned `assessment_identity` and
`assessment_as_of`. Transmission, ACK, and actual facts would each carry an
explicit caller-owned source identity and identity epoch, together with an
explicit declared source/epoch relationship for this audit. It would reject a
command, command factory, raw EMS or strategy request, runtime, adapter,
session, continuation, handoff boundary, prepared request, trace, receipt,
endpoint, credential, socket, transport, or historical assessment as authority.

The prospective output would be immutable PASS/GAP audit evidence only. It
would retain no live input and expose no command, adapter, runtime, session,
continuation, request, factory, hydration, copy-to-authority, replay, or
transmission authority.

## Candidate fact and authority semantics

- The transmission identity, source identity, and identity epoch are
  caller-owned and inert. They are audit subjects, never permissions to issue
  or repeat a command.
- ACK correlation must be explicit and exact against the declared transmission
  identity, source identity, identity epoch, and declared source/epoch
  relationship. Missing, unknown, malformed, stale, conflicting, mismatched,
  or relationship-undeclared correlation facts fail closed as GAP; a correlated
  ACK is not physical completion.
- Actual is a distinct caller-supplied observation fact. It cannot manufacture
  authority, prove transmission, or replace P0.3 retained actual/reconciliation.
  Its source identity and identity epoch must also conform to the same explicit
  declared relationship; absent, unknown, conflicting, or undeclared facts are
  GAP rather than an inferred match.
- `assessment_identity` and `assessment_as_of` are caller-owned audit facts,
  distinct from the other declared identities. They make the audit scope and
  time explicit; they do not create a clock, freshness inference, or history.
- Missing or unavailable ACK/actual facts remain explicit GAP/fail-closed audit
  evidence. They are not inferred as zero power, success, recovery, device
  availability, logical execution, or physical completion.
- Historical evidence cannot be hydrated, resumed, cloned, re-numbered, or
  replayed into a future audit or command path. A later audit would require a
  new caller-owned input and separate explicit identity/time facts.

## Frozen predecessors and non-goals

P0.1–P0.10, Residential EMS 1.0, and Campaign A–F are frozen. This candidate
does not modify their behavior, public APIs, numerical results, or authority
boundaries.

It does not authorize or include protocol, network, HTTP, Modbus, CAN, serial,
threading, scheduling, persistence, retries, HIL, PCS/BMS/DSP/STM32
integration, hardware control, field control, safety certification, or product
deployment.

## Future authorization and evidence gate

This ADR defines no implemented behavior and records no completed test,
mutation, CI, review, PR, or release evidence. Any future implementation would
need separate user authorization and an explicit specification, focused tests,
independent producer-corruption mutations, frozen-path regression, full
pytest/static/pre-commit terminal evidence, independent review, and a separate
user publication decision.
