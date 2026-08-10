# ADR-087 — Phase 9 EMS Strategy Layer Architecture

## Status

Accepted as the Phase 9 architecture baseline before TASK-090. This ADR freezes
contracts and dependency direction only; it introduces no production implementation.

## Context

EOS EMS Simulator 1.0 can execute explicit 24-hour scenarios, apply deterministic
component physics, preserve execution evidence, and export engineering results. Its
simple PV-surplus rule is a Demo fixture used to prove the simulator. It is not a
production EMS strategy boundary.

Phase 9 needs an independent layer that decides what Battery behavior to request while
leaving physical feasibility and deterministic execution to their existing owners. The
architecture must support future Self Consumption, Zero Export, TOU, and MPC strategies
without moving strategy code into the simulator or changing Phase 5–8 contracts.

## Decision

Freeze the following one-way flow:

```text
Facts
  |
  v
EMSContext
  |
  v
EMSStrategyBoundary
  |
  v
EMSDecision
  |
  v
Constraint / Feasibility
  |
  v
BatterySimulationActuation
  |
  v
Existing Simulator
```

### EMS and Simulator separation

The EMS Strategy Layer produces a decision request. The Simulator executes an explicit,
feasible actuation, evaluates physical state transition, and records evidence.

The following dependency and control flows are forbidden:

- Simulator calling or selecting an EMS Strategy;
- EMS Strategy advancing a simulation step or simulation time;
- EMS Strategy reading Simulator-owned mutable state;
- EMS Strategy controlling a Device or producing a Command.

Application composition outside both layers supplies facts, selects the strategy,
coordinates feasibility evaluation, and performs the explicit handoff to simulation.

### Decision and Actuation separation

`EMSDecision` is an immutable strategy request. `BatterySimulationActuation` is an
immutable input accepted by the existing Simulator. They are different artifacts and
must not be aliases, subclasses, or implicit conversions of one another.

The Phase 5 semantic `DecisionIntent` remains unchanged and expresses only
`charge`, `discharge`, or `idle`. `EMSDecision.requested_power_kw` is a finite,
non-negative raw kW magnitude. Direction comes from the semantic action:

- `charge` requires a positive requested magnitude;
- `discharge` requires a positive requested magnitude;
- `idle` requires a zero requested magnitude.

Only an explicit post-feasibility handoff maps this semantic action and magnitude to the
Simulator convention: charging is positive Battery power, discharging is negative, and
idle is zero. This mapping does not turn an `EMSDecision` into a Command.

### Strategy and Constraint separation

Strategy owns business objectives and decision logic. Constraint/Feasibility owns SOC
limits, Battery power limits, system capability limits, and physical feasibility.

A Strategy may observe facts such as SOC or limits when its business rule requires those
facts, but its requested decision never replaces an independent feasibility result.
The Simulator's physics protection remains a final physical validation and is not a
substitute for upstream feasibility evaluation.

### EMSContext

`EMSContext` is a frozen, slotted, immutable snapshot containing exact references to:

- the source decision context;
- objective evidence;
- active capability information.

The selected capability descriptor must be the exact descriptor present in the supplied
active capability evidence. Identity membership uses `is`, not value equality.

`EMSContext` owns no cache, history, Runtime state, clock, model execution, or Device
access. It neither derives future facts nor normalizes, copies, serializes, or reconstructs
its sources.

### EMSStrategyBoundary

The frozen interface shape is:

```text
evaluate(context: EMSContext) -> EMSDecision
```

The boundary is abstract, empty-slotted, and stateless. One evaluation accepts exactly
one context and returns exactly one decision. It does not mutate the context, execute a
Constraint, call the Simulator, retain history, retry, schedule, or dispatch. A concrete
strategy may hold only caller-supplied immutable configuration; configuration is not
Runtime state.

### EMSDecision

`EMSDecision` is frozen and slotted and contains:

- `source_context`: the exact `EMSContext` supplied to evaluation;
- `source_strategy`: the exact immutable strategy descriptor identifying the producer;
- `intent`: the exact semantic Phase 5 `DecisionIntent` created for this evaluation;
- `requested_power_kw`: the requested non-negative raw kW magnitude.

The following distinctions are permanent:

```text
EMSDecision != Command
EMSDecision != Feasible Decision
EMSDecision != BatterySimulationActuation
```

### Decision provenance

The evidence chain is:

```text
DecisionContext
  |
  v
EMSContext
  |
  v
Strategy
  |
  v
EMSDecision
  |
  v
Feasible Decision
  |
  v
BatterySimulationActuation
  |
  v
Simulation Trace
```

Each boundary preserves the exact direct source references it claims. Provenance uses
identity relationships, never only equal values. `copy`, `deepcopy`, serialization-based
reconstruction, and value-only lineage are forbidden.

This does not imply that unrelated Phase 4, Phase 5, and Simulator artifacts are
automatically connected. Application composition must create every explicit boundary
relationship and preserve the corresponding direct identities.

### Objective and Capability relationship

An Objective describes a business goal. A Capability describes an available system
ability. A Strategy evaluates facts and produces a decision request.

Objective does not directly generate Intent. `CapabilityDescriptor` is not a Strategy
implementation. Capability code does not call or instantiate a Strategy. The caller owns
strategy selection and may bind a Strategy to exact active objective/capability evidence.

### Future strategy extensions

Future Self Consumption, Zero Export, and TOU implementations conform to the same
boundary and return the same `EMSDecision` contract. They do not move SOC, Grid, Device,
or Simulator responsibilities into the strategy layer.

MPC is a future Strategy implementation, not a new Simulator mode and not an
`EMSDecision`. Forecasts and planning data must be supplied through a separate,
caller-owned immutable horizon artifact. The base `EMSContext` must not be polluted with
MPC-specific solver state, mutable forecasts, or optimization ownership.

## Dependency direction

Allowed direction:

```text
application composition
        |
        v
EMS Strategy Layer -> existing immutable decision/objective/capability contracts
        |
        v
explicit feasibility and simulation handoff
        |
        v
existing Simulator contracts
```

Phase 5–8 contracts do not depend on Phase 9 strategy implementations. The Strategy Layer
does not depend on Runtime, Scheduler, Device, Command, Dispatcher, communication
protocols, or concrete Simulator models.

## Consequences

- Production EMS algorithms can evolve without modifying simulation physics or execution.
- The same Strategy contract can be evaluated against real facts or caller-supplied test
  facts without knowing their transport source.
- Requested decisions, feasible decisions, simulation actuations, and Commands remain
  separately reviewable artifacts.
- Complete provenance requires explicit application composition and direct identity
  checks at every handoff.
- A later integration boundary is required before an `EMSDecision` can become a Simulator
  actuation; this ADR intentionally does not implement it.

## Non-goals

This ADR does not implement:

- Self Consumption, Zero Export, TOU, or MPC algorithms;
- optimization solvers or forecasts;
- Constraint implementations or feasibility algorithms;
- Simulator changes or simulation step progression;
- Runtime, Scheduler, Device, PCS, BMS, Command, or Dispatcher behavior;
- persistence, cache, history, telemetry, or cloud integration.

## Rejected alternatives

- Adding production EMS rules to `DailySimulationRunner`.
- Making the Simulator discover or invoke a Strategy.
- Treating `EMSDecision` as `BatterySimulationActuation` or as a Device Command.
- Moving SOC and power-limit enforcement into every Strategy implementation.
- Placing MPC horizon, solver state, or forecasts in the base `EMSContext`.
- Reconstructing provenance from serialized or value-equal artifacts.
