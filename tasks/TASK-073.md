# TASK-073 — Phase 6 Integration Validation

Status: IN REVIEW

## Objective

Validate the complete Phase 6 immutable simulation evidence flow using the
existing contracts from TASK-065～072.

TASK-073 adds integration tests and documentation only. It does not modify a
production contract, add a concrete production model, create a simulation
runner, calculate power balance, or introduce Runtime or Device execution.

## Validated flow

```text
SimulationStepIdentity
        |
        v
PV / Load / Tariff / Battery / Grid inputs
        |
        v
SimulationStepInput
        |
        v
test-only component models (each exactly once)
        |
        v
exact component results
        |
        v
SimulationState
        |
        v
SimulationStepResult

caller tuple[SimulationStepInput, ...]
        |
        v
SimulationScenario
```

## Integration scenarios

### Charging/import observation

- One exact timezone-aware step is shared by all component inputs.
- Battery actuation uses positive raw kW for charging.
- Grid exchange uses positive raw kW for import.
- Test-only models each receive their exact component input once.
- Battery source state remains unchanged and a distinct immutable next state
  is preserved.

### Discharging/export observation

- Battery actual power uses negative raw kW for discharging.
- Grid actual power uses negative raw kW for export.
- Aggregate construction does not invoke component models again.

### Caller-ordered scenario

- The exact caller tuple is preserved.
- Exact step input identities and caller order are preserved.
- No sorting, chronology inference, execution, or progression occurs.

## Identity and provenance validated

The integration tests verify:

- every component input references the exact step;
- every test-only model receives the exact component input;
- every component result references that exact input;
- Battery actuation preserves the exact feasible decision;
- Battery source and next states preserve their exact identities;
- `SimulationState` preserves every exact component result;
- `SimulationStepResult` preserves the exact aggregate input and state; and
- `SimulationScenario` preserves the exact caller tuple and elements.

## Exactly-once validation

Test-only recording models count their calls. Each PV, Load, Tariff, Battery,
and Grid model is called exactly once. Constructing `SimulationState`,
`SimulationStepResult`, and `SimulationScenario` does not execute a model or
advance a step.

These recording models exist only inside integration tests and are not
exported by the production `simulator` package.

## Files

- `tests/integration/test_phase6_simulation_flow.py`;
- `tasks/TASK-073.md`;
- `docs/EOS_学习手册.md`;
- `docs/EOS_架构说明.md`;
- `docs/TASK演进记录.md`.

## Non-goals

- No production code or public contract change.
- No concrete production PV, Load, Tariff, Battery, or Grid model.
- No component orchestration service or simulation runner.
- No power-balance, SOC-transition, energy, loss, or physics calculation.
- No step progression, Runtime, Scheduler, clock ownership, or loop.
- No Device, Command, Dispatch, PCS/BMS, protocol, persistence, cache, or
  history.

## Validation

Run:

```text
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
```
