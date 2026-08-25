# Residential Controlled Edge Runtime — P0.3

P0.3 has an explicit caller-driven tick: P0.2 start snapshot → P0.1 recovery
readiness → admission → safe request/ACK/actual/SOC → lifecycle reconciliation.
Only READY admits a new command; all other states pass no active command to the
plant.  A cleared fault never replays history.  Positive kW charges, negative
kW discharges, and SOC remains a fraction.  Production scheduling, protocol,
PCS/BMS/DSP I/O, HIL and persistence remain deferred.

Command provenance is closed: an admitted command is the exact `PowerCommand`
object supplied by the current `tick` caller, or it is absent. `tick(None)`
therefore admits no command. Trace, lifecycle, previous safety-final request,
ACK, actual telemetry and state/recovery facts are evidence only; none may
create, clone, renumber, retry, resume or replay a command. A recovery tick can
become `READY`, but READY means only that a later caller-supplied command may be
considered.

The admission result is independently checked against the current caller object
immediately before P0.2 `execute`. A selector that returns a forged command is
rejected before plant execution, so it cannot advance the virtual clock, SOC,
previous actual power, lifecycle book or returned runtime. This pre-execution
authority check is distinct from the trace contract below.

The P0.2 prepare phase has no clock, SOC or plant side effect. Its authority is
non-copyable and non-serializable; execute is one-shot. P0.3 retains one next
simulator only, while explicit P0.2 immutable branches remain scenario tests.

## Stage 2A state matrix

| State | Meaning in this prototype | New non-zero command admission | Normal guarded successors |
| --- | --- | --- | --- |
| `STARTING` | No admission observation has yet completed | No | waiting, ready, degraded, safe idle, faulted, shutdown |
| `WAITING_FOR_FRESH_TELEMETRY` | Required evidence is stale or unknown | No | waiting, ready, degraded, safe idle, faulted, shutdown |
| `READY` | Complete P0.1 readiness at a READY-start tick | Yes | waiting, ready, degraded, safe idle, faulted, shutdown |
| `DEGRADED` | Link/capability/lifecycle or execution evidence is unresolved | No | waiting, ready, degraded, safe idle, faulted, shutdown |
| `SAFE_IDLE` | Runtime deliberately retains a zero-request posture | No | waiting, ready, degraded, safe idle, faulted, shutdown |
| `FAULTED` | Critical fault, E-stop, or unexpected non-zero actual | No | waiting, ready, degraded, safe idle, faulted, shutdown |
| `SHUTTING_DOWN` | Explicit terminal software shutdown | No | shutdown only |

`ACTIVE` remains a wider P0.1 enum value, but P0.3 stage 2A has no producer for
it and never treats it as admission authority. State-before, state-after, and
stable transition reason codes are retained in every tick evidence record.

## Fact mapping and lifecycle policy

Telemetry/capability staleness, unknown SOC, and unknown actual power wait for
fresh facts. BMS/PCS disconnection or unavailability, unhealthy command channel
or runtime link, and non-terminal lifecycle records are degraded. Software
fallback, rejected/expired commands, and ordinary direction/reserve safety
blocks are safe-idle rather than device failures. A warning fault is evidence;
it does not alone revoke readiness. Critical BMS/PCS/Edge faults and E-stop are
faulted.

At tick start P0.3 expires lifecycle records before evaluating readiness. It has
no P0.3 public supersede API: an ACK drop/missing command remains in-flight and
blocks new admission. Terminal predecessor evidence does not bypass sequence or
identity validation.

## Stage 2B actual reconciliation and serializable evidence

Each tick retains five non-interchangeable facts: **caller request**,
**safety-final request**, **ACK accepted power**, **expected actual**, and
**Simulator actual telemetry**. The expectation is derived from the admitted
safety-final request only when application was authorized; an unauthorised or
safety-blocked non-zero actual is explicit unexpected-actual evidence. ACK
acceptance is not lifecycle completion: only retained actual telemetry with the
existing lifecycle timing/identity checks can support `COMPLETED`.

The classifier preserves every applicable reason and selects the primary reason
using one risk order: unexpected actual > unknown actual > mismatch > expired >
rejected ACK > delayed ACK > missing ACK > unauthorised application > lifecycle
incomplete > safety blocked > completed > actual matched > idle. Runtime state
consumes this primary classification fail-closed while the full list is audit
evidence.

`RuntimeLoopTrace` is immutable, versioned strict-schema evidence. It verifies
contiguous tick/time/state/SOC links but cannot hydrate a Runtime, Simulator,
lifecycle book or prepared session. It supplies no restart recovery, database,
transport, scheduler, thread, HIL or hardware authority.

Each step separately serializes the caller command, the admitted command,
`CommandOrigin` (`current_caller` or `none`) and an always-false
automatic-generation flag. These are audit facts, not a command-restoration
interface. Their strict validation is a post-execution audit defense: it checks
the retained record but cannot authorize a command or replace the independent
pre-execution current-caller identity guard.
