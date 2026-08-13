# TASK-128 - Explainable Daily MPC Integration

## Objective

Compose the existing physical MPC, explanation, CSV, feasibility, actuation,
and deterministic Simulator seams into one explicit caller-requested 24-hour
application flow.

## Contracts

`ExplainableMPCDailySimulationInput` owns an exact
`EMSIntegrationScenarioInput`, exactly 24 caller-supplied forecast horizons,
MPC configuration/objectives/strategy/model facts, one locale, and one
caller-owned CSV path. Every horizon's first timestamp must align with its
same-index daily simulation step.

`ExplainableMPCDailySimulationStepTrace` preserves each complete hour-level
chain: context, horizon, physical MPC result, explanation, formatted text,
journal record, CSV row, downstream provenance, feasible decision, handoff,
and simulator trace. `ExplainableMPCDailySimulationResult` preserves the 24
ordered traces, records, rows, daily result, serialized text, and file result.

## Execution semantics

The runner repeats one existing physical MPC cycle once for each of 24 explicit
caller-owned simulation steps. It creates each subsequent planning state from
the actual previous simulator battery state and grid result, never from MPC
projected SOC. It serializes and writes the CSV only once after all 24 steps
succeed. Any earlier failure stops immediately without partial CSV output.

## Responsibility separation

Forecast information remains planning information; daily PV/load/tariff curves
remain simulated actual facts. The journal record and CSV explain the MPC
decision request, not downstream execution: `FeasibleDecision`,
`ActuationHandoffResult`, and `SimulationExecutionTrace` remain separately
available in the per-step trace.

## Non-goals

No Runtime scheduler, clock, forecast generation, horizon padding, optimizer
rules, physics changes, feasibility changes, actuation changes, simulator
changes, EventJournal, directory creation, retry, device, or command behavior.
