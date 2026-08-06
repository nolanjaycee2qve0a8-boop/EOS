"""Tests for the Phase 6 simulation public API."""

from datetime import UTC, datetime

from kernel.decision import DecisionIntent, FeasibleDecisionIntent
from simulator import (
    BatterySimulationActuation,
    BatterySimulationInput,
    BatterySimulationModelBoundary,
    BatterySimulationResult,
    BatterySimulationState,
    GridSimulationInput,
    GridSimulationModelBoundary,
    GridSimulationResult,
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
    SimulationModelBinding,
    SimulationModelBindingCollection,
    SimulationScenario,
    SimulationState,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepResult,
    SingleStepSimulationExecutor,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)
from simulator import __all__ as public_names


def test_simulation_step_identity_public_import() -> None:
    step = SimulationStepIdentity(sequence=0, duration_seconds=1.0, timestamp=None)

    assert step.sequence == 0
    assert public_names == [
        "BatterySimulationActuation",
        "BatterySimulationInput",
        "BatterySimulationModelBoundary",
        "BatterySimulationResult",
        "BatterySimulationState",
        "GridSimulationInput",
        "GridSimulationModelBoundary",
        "GridSimulationResult",
        "LoadSimulationInput",
        "LoadSimulationModelBoundary",
        "LoadSimulationResult",
        "PVSimulationInput",
        "PVSimulationModelBoundary",
        "PVSimulationResult",
        "SimulationModelBinding",
        "SimulationModelBindingCollection",
        "SimulationScenario",
        "SimulationState",
        "SimulationStepIdentity",
        "SimulationStepInput",
        "SimulationStepResult",
        "SingleStepSimulationExecutor",
        "TariffSimulationInput",
        "TariffSimulationModelBoundary",
        "TariffSimulationResult",
    ]


def test_model_binding_contract_public_imports() -> None:
    assert SimulationModelBinding.__name__ == "SimulationModelBinding"
    assert (
        SimulationModelBindingCollection.__name__ == "SimulationModelBindingCollection"
    )


def test_single_step_executor_public_import() -> None:
    assert SingleStepSimulationExecutor.__name__ == "SingleStepSimulationExecutor"


def test_battery_actuation_public_import() -> None:
    feasible_decision = FeasibleDecisionIntent(DecisionIntent(1.0))

    actuation = BatterySimulationActuation(feasible_decision, 1.0)

    assert actuation.source_feasible_decision is feasible_decision


def test_battery_model_contract_public_imports() -> None:
    step = SimulationStepIdentity(0, 1.0, None)
    state = BatterySimulationState(0.5)
    actuation = BatterySimulationActuation(
        FeasibleDecisionIntent(DecisionIntent(1.0)),
        1.0,
    )
    simulation_input = BatterySimulationInput(step, state, actuation)
    result = BatterySimulationResult(simulation_input, state, 0.0)

    assert result.simulation_input is simulation_input
    assert result.next_state is state
    assert BatterySimulationModelBoundary.__name__ == ("BatterySimulationModelBoundary")


def test_grid_contract_public_imports() -> None:
    simulation_input = GridSimulationInput(
        SimulationStepIdentity(0, 1.0, None),
        2.0,
    )
    result = GridSimulationResult(simulation_input, 1.5)

    assert result.simulation_input is simulation_input
    assert GridSimulationModelBoundary.__name__ == "GridSimulationModelBoundary"


def test_aggregate_contract_public_imports() -> None:
    assert SimulationStepInput.__name__ == "SimulationStepInput"
    assert SimulationState.__name__ == "SimulationState"
    assert SimulationStepResult.__name__ == "SimulationStepResult"
    assert SimulationScenario.__name__ == "SimulationScenario"


def test_pv_contract_public_imports() -> None:
    simulation_input = PVSimulationInput(
        SimulationStepIdentity(0, 1.0, None),
        2.0,
    )

    result = PVSimulationResult(simulation_input, 1.0)

    assert result.simulation_input is simulation_input
    assert PVSimulationModelBoundary.__name__ == "PVSimulationModelBoundary"


def test_load_contract_public_imports() -> None:
    simulation_input = LoadSimulationInput(
        SimulationStepIdentity(0, 1.0, None),
        2.0,
    )
    result = LoadSimulationResult(simulation_input, 1.0)

    assert result.simulation_input is simulation_input
    assert LoadSimulationModelBoundary.__name__ == "LoadSimulationModelBoundary"


def test_tariff_contract_public_imports() -> None:
    simulation_input = TariffSimulationInput(
        SimulationStepIdentity(0, 1.0, datetime(2026, 8, 5, tzinfo=UTC)),
        0.8,
        0.3,
    )
    result = TariffSimulationResult(simulation_input, 0.8, 0.3)

    assert result.simulation_input is simulation_input
    assert TariffSimulationModelBoundary.__name__ == "TariffSimulationModelBoundary"
