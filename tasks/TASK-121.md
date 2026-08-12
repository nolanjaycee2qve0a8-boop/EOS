# TASK-121 - Physically-Aware Price Baseline Revision

## Objective

Add one deterministic, evidence-preserving physical revision path for the
existing price-only baseline candidate. The path produces a final optimization
solution that satisfies the implemented battery SOC and directional power
constraints without changing any existing frozen contract.

## Evidence chain

```text
Price Candidate
    -> Candidate SOC / power evidence
    -> Candidate aggregate
    -> Revision evidence
    -> Final solution
    -> Final SOC / power evidence
    -> Final aggregate
```

The candidate is retained exactly. `BatterySolutionRevision` maps each exact
candidate step to a distinct exact final step and records typed reasons in a
deterministic order: power limit before SOC limit.

## Revision semantics

The one-pass reviser processes caller order using the current revised SOC. It
restricts only charge/discharge magnitude by max power and SOC headroom, never
reverses an action, and turns a zero allowable directional request into idle.
Charge efficiency is multiplicative; discharge efficiency is divisive, matching
TASK-117. A narrowly scoped one-ULP inward adjustment prevents floating-point
boundary noise from weakening TASK-118's strict evaluation semantics.

## Responsibility separation

- Candidate physical evidence explains the original price-only proposal.
- Physical revision creates a separate final solution from that evidence.
- Final evidence verifies the final solution exactly once.
- Strategy feasibility remains a separate downstream concern.

## Non-goals

No solver search, retry loop, SOC clamping, grid rule, PV/load balance,
Actuation, Simulator, Runtime, Device, Command, or external solver framework.
Unsupported objectives remain unavailable with an empty final solution; an empty
feasible aggregate never changes that optimization outcome.
