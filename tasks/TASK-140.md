# TASK-140 - Rolling PV Opportunity Window

## Objective

Select one relevant next/current PV-surplus opportunity from a caller-owned
`ForecastHorizon` before a later task adapts that evidence into TASK-132
headroom accounting.

## Public contracts

- `PVOpportunityWindowConfiguration`
- `PVOpportunityWindowSelectionInput`
- `PVOpportunityWindowStep`
- `PVOpportunityWindow`
- `PVOpportunityWindowSelectionBoundary`
- `DeterministicPVOpportunityWindowSelector`

All artifacts are frozen/slotted. The selection input preserves exact forecast
horizon and configuration references; every selected step preserves the exact
source `ForecastPoint` object, original order, and source index.

## Opportunity semantics

An active point has `max(pv_power_kw - load_power_kw, 0) > 0`. Raw PV power,
price, battery state/model, DecisionIntent, energy, and simulator facts are not
used.

The selector finds the first active point in caller order. It then keeps the
same contiguous opportunity while an inactive gap has no more points than
`max_inactive_gap_points` **and** surplus resumes. A trailing temporary gap,
or a gap that exceeds tolerance, is discarded. Clearly separated later
opportunities are not merged or selected.

## Examples

With a maximum gap of one, `A A 0 A A 0 0 A` selects `A A 0 A A`; the final
two inactive points and the later second opportunity are excluded. A horizon
that starts with surplus selects the remaining current opportunity from index
zero.

## Architectural progression

- TASK-132 calculates headroom from all supplied forecast surplus points.
- TASK-139 proved that a repeating 24-point horizon can repeatedly count a
  near-complete PV day and become conservative.
- TASK-140 provides explicit first-opportunity selection evidence only.

## Explicit limitation

TASK-140 does not modify TASK-132, construct a sliced `ForecastHorizon`, or
alter GridChargeReservation, candidate planning, physical revision, MPC,
daily runner, or demo behavior. TASK-139 therefore remains unchanged until a
later composition task consumes this window evidence.
